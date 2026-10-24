# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from core.models import AuditEvent, Dealership, Membership
from customers.models import Customer
from inventory.models import Vehicle
from inventory.forms import VehicleForm
from . import tests as workflow_tests
from .models import DraftDeal, DraftTradeIn, DealEvent


@override_settings(TRADE_INTAKE_DEMO_ENABLED=True)
class TradeWorkflowTests(TestCase):
    def setUp(self):
        workflow_tests.DraftWorkflowTests.setUp(self)
        self.client.post(reverse('deal_create'), self.data)
        self.deal = DraftDeal.objects.get()
        self.edit_url = reverse('trade_edit', args=[self.deal.pk])
        self.details = dict(vin='SYNTHETIC-TRADE-001', year='2012', make='Test', model='Trade',
            title_brand='rebuilt', odometer_reading='123456', odometer_unit='miles', odometer_status='not_actual',
            lienholder_name='Synthetic payoff recipient', payoff_good_through='2026-11-15',
            trade_allowance='1500.00', trade_payoff='2500.00', notes='Synthetic title review notes')

    def save(self, **changes):
        self.deal.refresh_from_db()
        return self.client.post(self.edit_url, {**self.details, 'revision':self.deal.revision, **changes})

    def trade(self):
        return self.deal.trades.get(archived_at__isnull=True)

    def intake(self, **changes):
        self.deal.refresh_from_db()
        return self.client.post(reverse('trade_intake', args=[self.deal.pk,self.trade().pk]),
            {'revision':self.deal.revision,'stock_number':'TRADE-001','acquisition_cost':'1750.25','confirm':'on', **changes})

    def test_trade_identity_and_single_authoritative_money_use_reference_balance(self):
        self.assertEqual(self.save(vin='synthetic-trade-001').status_code,302)
        trade=self.trade();self.deal.refresh_from_db()
        self.assertEqual(trade.vin,'SYNTHETIC-TRADE-001')
        self.assertEqual(self.deal.draft_balance,Decimal('10600.10'))
        self.assertEqual(Vehicle.objects.count(),1)
        snap=DealEvent.objects.filter(deal=self.deal).first().snapshot
        self.assertEqual(snap['trades'][0]['title_brand'],'rebuilt')
        self.assertEqual(snap['trade_payoff'],'2500.00')
        self.assertContains(self.client.get(reverse('deal_detail',args=[self.deal.pk])), 'Synthetic payoff recipient')

    def test_blank_and_zero_mileage_and_unknown_title_are_distinct(self):
        self.assertEqual(self.save(odometer_reading='',odometer_unit='unknown',odometer_status='unknown',title_brand='unknown').status_code,302)
        self.assertIsNone(self.trade().odometer_reading)
        self.assertEqual(self.trade().title_brand,'unknown')
        self.assertEqual(self.save(odometer_reading='0',odometer_status='actual').status_code,302)
        self.assertEqual(self.trade().odometer_reading,0)

    def test_invalid_identity_and_mileage_preserve_work_and_do_not_write(self):
        for changes in [dict(vin='',year='',make='',model=''),dict(odometer_reading='-1'),dict(odometer_unit='unknown'),dict(title_brand='invented'),dict(payoff_good_through='2026-02-30'),dict(trade_allowance='999999')]:
            response=self.save(**changes)
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.context['form'].errors)
            self.assertContains(response,'Synthetic payoff recipient')
        self.assertFalse(DraftTradeIn.objects.exists())
        self.assertEqual(DealEvent.objects.count(),1)
        self.vehicle.vin=self.details['vin'];self.vehicle.save()
        self.assertTrue(self.save().context['form'].errors)

    def test_vin_only_draft_allowed_but_missing_identity_blocks_intake(self):
        self.assertEqual(self.save(year='',make='',model='').status_code,302)
        response=self.intake()
        self.assertContains(response,'Add the VIN, year, make and model')
        self.assertEqual(Vehicle.objects.count(),1)

    def test_noop_stale_trade_and_worksheet_revision_protect_each_other(self):
        self.save();self.save()
        self.assertEqual(DealEvent.objects.count(),2)
        self.assertEqual(self.save(revision=1,notes='Preserve this stale work').status_code,409)
        self.assertEqual(self.trade().notes,self.details['notes'])
        response=self.client.post(reverse('deal_detail',args=[self.deal.pk]),{**self.data,'revision':1,'notes':'Old desk'})
        self.assertEqual(response.status_code,409)
        self.assertEqual(DealEvent.objects.count(),2)

    def test_intake_copies_once_preserves_identity_and_separates_cost_from_money(self):
        self.save();before=list(DealEvent.objects.order_by('pk').values_list('snapshot',flat=True))
        response=self.intake();self.assertEqual(response.status_code,302)
        trade=self.trade();vehicle=trade.inventory_vehicle
        self.assertEqual((vehicle.vin,vehicle.title_brand,vehicle.odometer_status,vehicle.acquisition_cost),('SYNTHETIC-TRADE-001','rebuilt','not_actual',Decimal('1750.25')))
        self.assertEqual(vehicle.odometer_reading,123456)
        self.assertEqual(vehicle.status,'acquired');self.assertFalse(vehicle.title_received)
        self.assertEqual(vehicle.notes,'')
        self.assertEqual(AuditEvent.objects.filter(vehicle=vehicle).count(),1)
        self.assertEqual(self.intake(revision=1).url,response.url)
        self.assertEqual(Vehicle.objects.count(),2)
        self.assertEqual(DealEvent.objects.count(),3)
        self.assertEqual(list(DealEvent.objects.order_by('pk').values_list('snapshot',flat=True))[:2],before)
        self.save(vin='ATTACK',title_brand='unbranded',year='2020',make='Changed',model='Changed')
        self.assertEqual(self.trade().vin,'SYNTHETIC-TRADE-001')
        self.assertEqual(self.trade().title_brand,'rebuilt')
        vehicle.vin='CORRECTED-INVENTORY';vehicle.save()
        self.assertEqual(self.trade().vin,'SYNTHETIC-TRADE-001')

    def test_intake_requires_review_cost_unique_stock_and_own_dealer_vin(self):
        self.save()
        for changes in [dict(confirm=''),dict(acquisition_cost=''),dict(stock_number='A'),dict(acquisition_cost='-1'),dict(revision=1)]:
            self.assertIn(self.intake(**changes).status_code,(200,409))
            self.assertEqual(Vehicle.objects.count(),1)
        duplicate=Vehicle.objects.create(dealership=self.dealer,stock_number='OTHER',vin=self.details['vin'],year=2012,make='Test',model='Trade')
        self.assertContains(self.intake(),'already in this dealership')
        duplicate.dealership=self.other;duplicate.save()
        self.assertEqual(self.intake().status_code,302)  # No cross-dealer VIN disclosure/block.

    def test_intake_ignores_forged_links_and_cross_dealer_routes_are_hidden(self):
        self.save(inventory_vehicle=self.vehicle.pk,deal=999999)
        self.assertIsNone(self.trade().inventory_vehicle_id)
        other_deal=DraftDeal.objects.create(dealership=self.other,vehicle=self.vehicle,buyer=self.foreign)
        foreign_trade=DraftTradeIn.objects.create(deal=other_deal,vin='PRIVATE-VIN')
        for route in ('trade_remove','trade_intake'):
            self.assertEqual(self.client.get(reverse(route,args=[self.deal.pk,foreign_trade.pk])).status_code,404)
            self.assertEqual(self.client.get(reverse(route,args=[other_deal.pk,foreign_trade.pk])).status_code,404)
        self.assertEqual(self.client.get(reverse('trade_edit',args=[other_deal.pk])).status_code,404)

    def test_viewer_denied_and_intake_production_gate_is_enforced(self):
        self.save();trade=self.trade()
        with override_settings(TRADE_INTAKE_DEMO_ENABLED=False):
            self.assertEqual(self.intake().status_code,404)
            response=self.client.get(reverse('deal_detail',args=[self.deal.pk]))
            self.assertNotContains(response,reverse('trade_intake',args=[self.deal.pk,trade.pk]))
        self.member.role='viewer';self.member.save()
        for url in [self.edit_url,reverse('trade_remove',args=[self.deal.pk,trade.pk]),reverse('trade_intake',args=[self.deal.pk,trade.pk])]:
            self.assertEqual(self.client.get(url).status_code,403)
            self.assertEqual(self.client.post(url,{}).status_code,403)
        self.assertContains(self.client.get(reverse('deal_detail',args=[self.deal.pk])),'Synthetic payoff recipient')

    def test_remove_requires_review_keeps_inventory_and_history_and_allows_replacement(self):
        self.save(trade_payoff='500.00');self.intake();trade=self.trade();self.deal.refresh_from_db()
        url=reverse('trade_remove',args=[self.deal.pk,trade.pk])
        self.assertContains(self.client.get(url),'$9,600.10')
        payload={'revision':self.deal.revision,'reason':'Synthetic trade withdrawn','confirm':'on'}
        self.assertTrue(self.client.post(url,{**payload,'confirm':''}).context['form'].errors)
        self.assertEqual(self.client.post(url,{**payload,'revision':1}).status_code,409)
        self.assertEqual(self.client.post(url,payload).status_code,302)
        trade.refresh_from_db();self.deal.refresh_from_db()
        self.assertIsNotNone(trade.archived_at)
        self.assertEqual((self.deal.trade_allowance,self.deal.trade_payoff),(Decimal('0'),Decimal('0')))
        self.assertEqual(Vehicle.objects.count(),2)
        self.assertEqual(DealEvent.objects.first().snapshot['action'],'trade_removed')
        self.assertEqual(self.save(vin='SYNTHETIC-REPLACEMENT').status_code,302)
        self.assertEqual(self.deal.trades.count(),2)
        self.assertNotEqual(self.trade().pk,trade.pk)

    def test_negative_equity_removal_cannot_make_balance_negative(self):
        self.save(trade_allowance='0',trade_payoff='5000')
        self.deal.refresh_from_db();self.deal.down_payment=Decimal('15000');self.deal.save()
        self.deal.refresh_from_db();self.assertEqual(self.deal.draft_balance,Decimal('600.10'))
        response=self.client.post(reverse('trade_remove',args=[self.deal.pk,self.trade().pk]),{'revision':self.deal.revision,'reason':'Test','confirm':'on'})
        self.assertContains(response,'would make the draft balance negative')
        self.assertIsNone(self.trade().archived_at)

    def test_audit_failures_roll_back_trade_creation_intake_and_removal(self):
        with patch('deals.services.DealEvent.objects.create',side_effect=RuntimeError('unavailable')):
            with self.assertRaises(RuntimeError):self.save()
        self.assertFalse(DraftTradeIn.objects.exists())
        self.save();self.deal.refresh_from_db()
        with patch('deals.services.DealEvent.objects.create',side_effect=RuntimeError('unavailable')):
            with self.assertRaises(RuntimeError):self.intake()
        self.assertEqual(Vehicle.objects.count(),1)
        self.assertFalse(AuditEvent.objects.exists())
        self.assertIsNone(self.trade().inventory_vehicle_id)
        with patch('deals.services.DealEvent.objects.create',side_effect=RuntimeError('unavailable')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('trade_remove',args=[self.deal.pk,self.trade().pk]),{'revision':self.deal.revision,'reason':'Test','confirm':'on'})
        self.assertIsNone(self.trade().archived_at)
        self.deal.refresh_from_db();self.assertEqual(self.deal.trade_payoff,Decimal('2500'))

    def test_party_editor_cannot_use_its_trade_as_the_sale_vehicle(self):
        self.save();self.intake();self.deal.refresh_from_db()
        response=self.client.post(reverse('deal_edit',args=[self.deal.pk]),{**self.data,'vehicle':self.trade().inventory_vehicle_id,'revision':self.deal.revision})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.context['form'].errors)
        self.deal.refresh_from_db();self.assertEqual(self.deal.vehicle_id,self.vehicle.pk)

    def test_action_gets_do_not_mutate_and_posts_require_csrf(self):
        self.save();trade=self.trade()
        csrf_client=Client(enforce_csrf_checks=True);csrf_client.force_login(self.user)
        for route in ('trade_remove','trade_intake'):
            url=reverse(route,args=[self.deal.pk,trade.pk])
            self.assertEqual(self.client.get(url).status_code,200)
            self.assertEqual(csrf_client.post(url,{'revision':2,'confirm':'on'}).status_code,403)
        self.assertEqual(Vehicle.objects.count(),1)
        self.assertEqual(DealEvent.objects.count(),2)
        self.assertIsNone(self.trade().archived_at)

    def test_older_inventory_form_cannot_clear_intake_mileage(self):
        self.save();self.intake();vehicle=self.trade().inventory_vehicle
        data={name:getattr(vehicle,name) for name in VehicleForm.Meta.fields if not name.startswith('odometer_')}
        data['revision']=vehicle.revision
        form=VehicleForm(data,instance=vehicle)
        self.assertTrue(form.is_valid(),form.errors)
        form.save();vehicle.refresh_from_db()
        self.assertEqual(vehicle.odometer_reading,123456)
        self.assertEqual(vehicle.odometer_status,'not_actual')


@skipUnless(connection.vendor=='postgresql','Concurrent intake verification requires PostgreSQL')
@override_settings(TRADE_INTAKE_DEMO_ENABLED=True)
class ConcurrentTradeIntakeTests(TransactionTestCase):
    def test_simultaneous_intake_creates_one_vehicle_and_one_event(self):
        dealer=Dealership.objects.create(name='Synthetic concurrent intake')
        user=get_user_model().objects.create_user(username='trade-concurrent')
        Membership.objects.create(user=user,dealership=dealer,role='staff')
        vehicle=Vehicle.objects.create(dealership=dealer,stock_number='SALE',year=2020,make='Test',model='Sale')
        buyer=Customer.objects.create(dealership=dealer,first_name='Synthetic',last_name='Buyer')
        deal=DraftDeal.objects.create(dealership=dealer,vehicle=vehicle,buyer=buyer)
        trade=DraftTradeIn.objects.create(deal=deal,vin='SYNTHETIC-CONCURRENT',year=2010,make='Test',model='Trade')
        ready=Barrier(2)
        def submit():
            close_old_connections()
            try:
                client=Client();client.force_login(user);ready.wait(timeout=20)
                response=client.post(reverse('trade_intake',args=[deal.pk,trade.pk]),{'revision':1,'stock_number':'INTAKE','acquisition_cost':'1000','confirm':'on'})
                return response.status_code,response.get('Location')
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(submit) for _ in range(2)]
            results=[future.result(timeout=30) for future in futures]
        self.assertEqual([status for status,_ in results],[302,302])
        self.assertEqual(results[0][1],results[1][1])
        self.assertEqual(Vehicle.objects.count(),2)
        self.assertEqual(DealEvent.objects.count(),1)
        self.assertEqual(AuditEvent.objects.count(),1)

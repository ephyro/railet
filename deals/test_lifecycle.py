# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from core.models import Dealership, Membership
from customers.models import Customer
from inventory.models import Vehicle
from .models import DraftDeal, DraftTradeIn
from .services import persist_draft


class DraftLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer=Dealership.objects.create(name='Synthetic lifecycle dealer')
        cls.other=Dealership.objects.create(name='Other dealer')
        cls.users={}
        for name,role,dealer in [('staff','staff',cls.dealer),('viewer','viewer',cls.dealer),('foreign','owner',cls.other)]:
            user=get_user_model().objects.create_user(name);cls.users[name]=user
            Membership.objects.create(user=user,role=role,dealership=dealer)
        cls.vehicle=Vehicle.objects.create(dealership=cls.dealer,stock_number='SYN-ARCHIVE',year=2020,make='Synthetic',model='Sedan')
        cls.buyer=Customer.objects.create(dealership=cls.dealer,first_name='Riley',last_name='Demo')
        cls.deal=DraftDeal.objects.create(dealership=cls.dealer,vehicle=cls.vehicle,buyer=cls.buyer,sale_price=Decimal('10000'),down_payment=Decimal('1000'))

    def setUp(self):
        self.client.force_login(self.users['staff'])
        self.url=reverse('draft_lifecycle',args=[self.deal.pk])

    def change(self,action='archive',revision=1,reason='Synthetic abandoned draft'):
        return self.client.post(self.url,{'action':action,'revision':revision,'reason':reason})

    def test_archive_restore_history_and_money_preservation(self):
        self.assertEqual(self.change().status_code,302)
        self.deal.refresh_from_db();self.vehicle.refresh_from_db()
        self.assertIsNotNone(self.deal.archived_at)
        self.assertEqual(self.deal.archived_by,self.users['staff'])
        self.assertEqual(self.deal.revision,2)
        self.assertEqual(self.deal.draft_balance,Decimal('9000'))
        self.assertEqual(self.vehicle.status,Vehicle.Status.ACQUIRED)
        archive=self.deal.events.get().snapshot
        self.assertEqual(archive['action'],'draft_archived')
        self.assertEqual(archive['reason'],'Synthetic abandoned draft')
        self.assertEqual(self.change('restore',2,'Resume discussions').status_code,302)
        self.deal.refresh_from_db()
        self.assertIsNone(self.deal.archived_at)
        self.assertEqual(self.deal.revision,3)
        self.assertEqual(self.deal.events.count(),2)
        self.assertEqual(self.deal.events.first().snapshot['reason'],'Resume discussions')

    def test_retry_and_stale_action_do_not_toggle_state(self):
        self.change()
        self.assertEqual(self.change().status_code,409)
        self.assertEqual(self.change('restore',1).status_code,409)
        self.deal.refresh_from_db()
        self.assertIsNotNone(self.deal.archived_at)
        self.assertEqual(self.deal.events.count(),1)

    def test_reason_required_and_preserved_on_stale_submission(self):
        self.assertEqual(self.change(reason='   ').status_code,200)
        self.deal.refresh_from_db();self.assertIsNone(self.deal.archived_at)
        self.change()
        response=self.change(reason='Preserve this reason')
        self.assertContains(response,'Preserve this reason',status_code=409)

    def test_roles_scope_and_csrf(self):
        for name,status in [('viewer',403),('foreign',404)]:
            self.client.force_login(self.users[name]);self.assertEqual(self.change().status_code,status)
        self.assertEqual(DraftDeal.objects.get(pk=self.deal.pk).events.count(),0)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.users['staff'])
        self.assertEqual(strict.post(self.url,{'action':'archive','revision':1,'reason':'Synthetic'}).status_code,403)
        self.assertEqual(self.client.put(self.url).status_code,405)

    def test_lists_hide_archived_by_default_and_allow_explicit_scope(self):
        self.change()
        self.assertEqual(len(self.client.get(reverse('deals')).context['deals']),0)
        for scope in ('archived','all'):
            self.assertEqual(len(self.client.get(reverse('deals'),{'scope':scope}).context['deals']),1)
        self.assertEqual(len(self.client.get(reverse('deals'),{'scope':'bad'}).context['deals']),0)

    def test_archived_workspace_and_party_edits_blocked(self):
        self.change()
        detail=self.client.get(reverse('deal_detail',args=[self.deal.pk]))
        self.assertContains(detail,'Archived draft')
        self.assertNotContains(detail,'>Save deal</button>')
        self.assertEqual(self.client.post(reverse('deal_detail',args=[self.deal.pk]),{'revision':2,'sale_price':'1'}).status_code,409)
        self.assertEqual(self.client.get(reverse('deal_edit',args=[self.deal.pk])).status_code,409)
        self.deal.refresh_from_db();self.assertEqual(self.deal.sale_price,Decimal('10000'))

    def test_archived_trade_routes_blocked_and_trade_record_retained(self):
        trade=DraftTradeIn.objects.create(deal=self.deal,vin='SYNTHETIC-TRADE')
        self.change()
        for route,args in [('trade_edit',[self.deal.pk]),('trade_remove',[self.deal.pk,trade.pk]),('trade_intake',[self.deal.pk,trade.pk])]:
            self.assertEqual(self.client.post(reverse(route,args=args),{}).status_code,403)
        trade.refresh_from_db();self.assertIsNone(trade.archived_at)

    def test_service_does_not_allow_stale_object_to_edit_archived_draft(self):
        stale=DraftDeal.objects.get(pk=self.deal.pk)
        self.change()
        stale.sale_price=Decimal('1')
        with self.assertRaises(ValidationError):persist_draft(stale,actor=self.users['staff'])
        self.deal.refresh_from_db();self.assertEqual(self.deal.sale_price,Decimal('10000'))

    def test_event_failure_rolls_back_archival(self):
        with patch('deals.services.DealEvent.objects.create',side_effect=RuntimeError('synthetic audit failure')):
            with self.assertRaises(RuntimeError):self.change()
        self.deal.refresh_from_db()
        self.assertIsNone(self.deal.archived_at);self.assertEqual(self.deal.revision,1)

    def test_corrupt_cross_dealership_customer_is_not_exposed(self):
        customer=Customer.objects.create(dealership=self.other,first_name='Private',last_name='Foreign synthetic')
        DraftDeal.objects.filter(pk=self.deal.pk).update(buyer=customer)
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.assertEqual(self.change().status_code,404)
        self.assertEqual(self.deal.events.count(),0)

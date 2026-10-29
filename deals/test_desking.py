# SPDX-License-Identifier: MPL-2.0
from datetime import date
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase,TestCase,override_settings,Client
from django.urls import reverse
from core.models import AuditEvent
from inventory.models import Vehicle
from customers.models import Customer,CustomerEvent
from .models import DraftDeal,DealEvent
from .florida_tax import COUNTIES,estimate
from .desking import illustrate
from . import tests as fixtures

class FloridaTaxReferenceTests(SimpleTestCase):
    def calc(self,**changes):
        args=dict(county='Miami-Dade',on=date(2026,10,29),sale_price='10000',dealer_fee='0',trade_allowance='0',title_registration='0');args.update(changes);return estimate(**args)
    def test_independent_state_county_cap_and_2026_rates(self):
        self.assertEqual(len(COUNTIES),67)
        self.assertEqual(self.calc()['total'],'650.00')
        self.assertEqual(self.calc(sale_price='4000')['total'],'280.00')
        self.assertEqual(self.calc(sale_price='5000')['total'],'350.00')
        self.assertEqual(self.calc(county='Palm Beach')['total'],'625.00')
        self.assertEqual(self.calc(county='Martin')['total'],'625.00')
        self.assertEqual(self.calc(county='Citrus')['total'],'600.00')
        self.assertEqual(self.calc(county='Hamilton')['total'],'700.00')
    def test_trade_gross_allowance_and_taxable_fee_but_not_down_or_payoff(self):
        result=self.calc(dealer_fee='299',trade_allowance='2000',trade_confirmed=True,title_registration='150',title_confirmed=True)
        self.assertEqual(result['taxable_base'],'8299');self.assertEqual(result['total'],'547.94')
        self.assertEqual(self.calc(trade_allowance='12000',trade_confirmed=True)['total'],'0.00')
        for args in ({'trade_allowance':'1'},{'title_registration':'1'},{'county':'unknown'},{'on':date(2027,1,1)},{'sale_price':1.25}):
            with self.assertRaises(ValidationError):self.calc(**args)
    def test_aggregate_invoice_rounding_and_components_tie(self):
        result=self.calc(sale_price='0.08');self.assertEqual(result['total'],'0.01');self.assertEqual(result['rounding_adjustment'],'0.01')
        self.assertEqual(sum(Decimal(result[k]) for k in ('state_tax','county_tax','rounding_adjustment')),Decimal('0.01'))
        self.assertEqual(self.calc(sale_price='100.08')['total'],'7.01')

class DeskingIllustrationTests(SimpleTestCase):
    def test_precomputed_supplied_charge_final_cent_and_zero_rate(self):
        result=illustrate(balance='1000',method='precomputed',frequency='monthly',count=3,finance_charge='100')
        self.assertEqual((result['payment'],result['final_payment'],result['total_payments']),('366.67','366.66','1100'))
        result=illustrate(balance='1000',method='simple',frequency='monthly',count=10,rate='0')
        self.assertEqual((result['payment'],result['final_payment'],result['finance_charge']),('100.00','100.00','0.00'))
    def test_monthly_periodic_reference_and_unknown_terms(self):
        result=illustrate(balance='10000',method='simple',frequency='monthly',count=36,rate='12')
        self.assertEqual(result['payment'],'332.14');self.assertIn('Actual daily-interest',result['note'])
        for changes in ({'method':'precomputed'},{'frequency':'weekly'},{'count':None},{'rate':None}):
            args=dict(balance='1000',method='simple',frequency='monthly',count=12,rate='12');args.update(changes)
            self.assertFalse(illustrate(**args)['available'])

@override_settings(FL_TAX_ESTIMATES_ENABLED=True)
class DealDeskingTests(TestCase):
    def setUp(self):
        fixtures.DraftWorkflowTests.setUp(self)
        self.data.update(deal_type='bhph',tax_mode='fl',tax_county='Miami-Dade',tax_date='2026-10-29')
    def proposal(self):return {'bhph-included':'1','bhph-interest_method':'precomputed','bhph-payment_frequency':'monthly','bhph-payment_count':'12','bhph-illustration_finance_charge':'1200','bhph-annual_contract_rate':'','bhph-first_payment_date':''}
    def test_automatic_tax_is_server_computed_and_context_retained(self):
        response=self.client.post(reverse('deal_create'),{**self.data,'tax':'0.01',**self.proposal()});self.assertEqual(response.status_code,302)
        deal=DraftDeal.objects.get();self.assertEqual(deal.tax,Decimal('650.01'));self.assertEqual(deal.draft_balance,Decimal('9650.11'))
        self.assertEqual(deal.tax_context['county'],'Miami-Dade');self.assertEqual(deal.events.get().snapshot['tax_context'],deal.tax_context)
        self.assertEqual(deal.finance_proposals.get(kind='bhph').illustration_finance_charge,Decimal('1200'))
        self.assertEqual(deal.events.get().snapshot['finance_proposals']['bhph']['illustration_finance_charge'],'1200.00')
    def test_inline_vehicle_customer_and_draft_saved_once_and_audited(self):
        data={**self.data,'vehicle_mode':'new','vehicle':'','newvehicle-stock_number':'INLINE-1','newvehicle-year':'2020','newvehicle-make':'Synthetic','newvehicle-model':'Desk Sedan','customer_mode':'new','buyer':'','new-first_name':'New Desk','new-last_name':'Synthetic',**self.proposal()}
        first=self.client.post(reverse('deal_create'),data);self.assertEqual(first.status_code,302)
        deal=DraftDeal.objects.get();self.assertEqual(deal.vehicle.stock_number,'INLINE-1');self.assertEqual(deal.vehicle.title_brand,'unknown')
        self.assertEqual(AuditEvent.objects.filter(vehicle=deal.vehicle,action='created').count(),1)
        self.assertEqual(CustomerEvent.objects.filter(customer=deal.buyer).count(),1)
        self.assertEqual(self.client.post(reverse('deal_create'),data).url,first.url)
        self.assertEqual(Vehicle.objects.filter(stock_number='INLINE-1').count(),1)
    def test_validation_and_audit_failure_roll_back_inline_records(self):
        data={**self.data,'vehicle_mode':'new','vehicle':'','newvehicle-stock_number':'ROLLBACK','newvehicle-year':'2020','newvehicle-make':'Synthetic','newvehicle-model':'Desk Sedan','customer_mode':'new','buyer':'','new-first_name':'Rollback','new-last_name':'Synthetic'}
        with patch('deals.services.DealEvent.objects.create',side_effect=RuntimeError('Invented failure')):
            with self.assertRaises(RuntimeError):self.client.post(reverse('deal_create'),data)
        self.assertFalse(Vehicle.objects.filter(stock_number='ROLLBACK').exists());self.assertFalse(Customer.objects.filter(first_name='Rollback').exists())
        response=self.client.post(reverse('deal_create'),{**data,'tax_county':''});self.assertEqual(response.status_code,200)
        self.assertContains(response,'registration county');self.assertFalse(Vehicle.objects.filter(stock_number='ROLLBACK').exists())
    def test_existing_draft_manual_tax_preserved_until_explicit_switch(self):
        data={k:v for k,v in self.data.items() if not k.startswith('tax_')};self.client.post(reverse('deal_create'),data)
        deal=DraftDeal.objects.get();self.assertEqual(deal.tax,Decimal('600.00'));self.assertEqual(deal.tax_context,{})
        self.client.post(reverse('deal_detail',args=[deal.pk]),{**self.data,'revision':deal.revision,'tax':'0'})
        deal.refresh_from_db();self.assertEqual(deal.tax,Decimal('650.01'))
    def test_no_guessed_county_trade_fee_or_out_of_state_tax(self):
        for changes in ({'tax_county':''},{'trade_allowance':'100'},{'title_registration':'100'},{'tax_date':'2027-01-01'},{'tax_mode':'manual','tax_reason':''}):
            response=self.client.post(reverse('deal_create'),{**self.data,**changes});self.assertEqual(response.status_code,200);self.assertFalse(DraftDeal.objects.exists())
        self.buyer.region='GA';self.buyer.save()
        response=self.client.post(reverse('deal_create'),self.data);self.assertContains(response,'out-of-state');self.assertFalse(DraftDeal.objects.exists())
    def test_preview_permissions_csrf_scope_and_no_writes(self):
        url=reverse('deal_estimate');response=self.client.post(url,{**self.data,**self.proposal()})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['tax']['total'],'650.01');self.assertFalse(DraftDeal.objects.exists())
        self.assertIn('no-store',response['Cache-Control']);self.assertEqual(self.client.get(url).status_code,405)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.user);self.assertEqual(strict.post(url,self.data).status_code,403)
        with override_settings(FL_TAX_ESTIMATES_ENABLED=False):self.assertEqual(self.client.post(url,self.data).status_code,403)

    def test_inline_duplicate_stock_and_vin_require_review_without_orphans(self):
        self.vehicle.vin='SYN-DUPLICATE';self.vehicle.save()
        data={**self.data,'vehicle_mode':'new','vehicle':'','newvehicle-stock_number':'NEW-VIN','newvehicle-vin':'SYN-DUPLICATE','newvehicle-year':'2020','newvehicle-make':'Synthetic','newvehicle-model':'VIN desk'}
        response=self.client.post(reverse('deal_create'),data);self.assertContains(response,'matching VINs');self.assertFalse(DraftDeal.objects.exists())
        response=self.client.post(reverse('deal_create'),{**data,'newvehicle-duplicate_review_acknowledged':'on','newvehicle-duplicate_review_reason':'Invented separate stock review'})
        self.assertEqual(response.status_code,302);self.assertEqual(AuditEvent.objects.get().changes['duplicate_vin_review']['after']['reason'],'Invented separate stock review')
        before=Customer.objects.count()
        response=self.client.post(reverse('deal_create'),{**data,'submission_key':str(uuid4()),'newvehicle-stock_number':'A','customer_mode':'new','buyer':'','new-first_name':'Not Saved','new-last_name':'Synthetic'})
        self.assertContains(response,'stock number already exists');self.assertEqual(Customer.objects.count(),before)

    def test_auto_tax_reprices_trade_and_removal_and_history_stays_frozen(self):
        self.client.post(reverse('deal_create'),self.data);deal=DraftDeal.objects.get();original=deal.events.get().snapshot
        data={'revision':deal.revision,'vin':'SYN-TRADE-AUTO','title_brand':'unknown','odometer_unit':'unknown','odometer_status':'unknown','trade_allowance':'2000','trade_payoff':'1000','tax_trade_confirmed':'on'}
        saved=self.client.post(reverse('trade_edit',args=[deal.pk]),data);self.assertEqual(saved.status_code,302)
        deal.refresh_from_db();self.assertEqual(deal.tax,Decimal('530.01'))
        self.assertEqual(deal.events.order_by('pk').first().snapshot,original)
        trade=deal.trades.get();result=self.client.post(reverse('trade_remove',args=[deal.pk,trade.pk]),{'revision':deal.revision,'reason':'Invented removal','confirm':'on'})
        self.assertEqual(result.status_code,302);deal.refresh_from_db();self.assertEqual(deal.tax,Decimal('650.01'))

    def test_manual_override_requires_reason_and_keeps_previous_auto_history(self):
        self.client.post(reverse('deal_create'),self.data);deal=DraftDeal.objects.get();original=deal.events.get().snapshot
        result=self.client.post(reverse('deal_detail',args=[deal.pk]),{**self.data,'revision':deal.revision,'tax_mode':'manual','tax':'123.45','tax_reason':'Invented special case for review'})
        self.assertEqual(result.status_code,302);deal.refresh_from_db();self.assertEqual(deal.tax,Decimal('123.45'))
        self.assertEqual(deal.tax_context['reason'],'Invented special case for review');self.assertEqual(deal.events.order_by('pk').first().snapshot,original)

    def test_unverifiable_saved_tax_metadata_fails_without_guessing_or_rewriting(self):
        deal=DraftDeal.objects.create(dealership=self.dealer,vehicle=self.vehicle,buyer=self.buyer,sale_price='10000',tax='600',tax_context=['invalid'])
        response=self.client.post(reverse('deal_detail',args=[deal.pk]),{**self.data,'revision':1})
        self.assertEqual(response.status_code,200);self.assertContains(response,'Saved tax information could not be verified')
        deal.refresh_from_db();self.assertEqual(deal.tax,Decimal('600.00'));self.assertEqual(deal.tax_context,['invalid']);self.assertFalse(deal.events.exists())

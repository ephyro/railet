# SPDX-License-Identifier: MPL-2.0
from datetime import date
from uuid import uuid4
from unittest.mock import patch
from django.test import TestCase,Client,override_settings
from django.urls import reverse
from . import test_payment_impact as payments
from . import test_servicing as references
from .services import record_receipt,reconcile,reverse_receipt


@override_settings(DEMO_LEDGER_ENABLED=True,DEMO_SERVICING_ENABLED=True)
class ReversalImpactTests(TestCase):
    @classmethod
    def setUpTestData(cls):references.ServicingIntegrationTests.setUpTestData.__func__(cls)
    select=payments.PaymentImpactTests.select
    record=payments.PaymentImpactTests.record
    def setUp(self):
        self.client.force_login(self.users['staff'])
        clock=patch('finance.servicing_services.timezone.localdate',return_value=date(2026,3,2));clock.start();self.addCleanup(clock.stop)
        self.select();self.original=self.record(amount='200.00',effective_on=date(2026,2,1))
        self.url=reverse('ledger_demo_reverse',args=[self.book.pk,self.original.pk]);self.confirm_url=reverse('ledger_demo_confirm')
        self.data={'effective_on':'2026-03-02','reference':'Invented duplicate entry','request_key':str(uuid4()),'synthetic_confirmed':'on'}
    def preview(self,**extra):return self.client.post(self.url,{**self.data,**extra})
    def confirm(self,token,action='post'):return self.client.post(self.confirm_url,{'preview_token':token,'action':action})

    def test_review_no_mutation_confirm_preserves_original_and_links_reversal(self):
        before=list(self.book.postings.values())
        response=self.preview();impact=response.context['payment_impact']
        self.assertContains(response,'Demo reversal impact');self.assertContains(response,'Reason for reversal')
        self.assertEqual((impact['before']['amount_due_cents'],impact['after']['amount_due_cents']),(0,20000))
        self.assertEqual((impact['before']['status'],impact['after']['status']),('current','past_due'))
        self.assertEqual(impact['after']['days_past_due'],29)
        self.assertEqual(impact['coverage'],[{'number':1,'due_on':'2026-02-01','amount':'$100.00'},{'number':2,'due_on':'2026-03-01','amount':'$100.00'}])
        self.assertEqual(list(self.book.postings.values()),before)
        result=self.confirm(response.context['token']);self.assertRedirects(result,reverse('bhph_account_receipt',args=[self.book.pk,self.original.pk]))
        correction=self.book.postings.get(kind='reversal');self.original.refresh_from_db()
        self.assertEqual(correction.reverses_id,self.original.pk);self.assertEqual(correction.amount_cents,20000)
        self.assertEqual(correction.reason,self.data['reference']);self.assertEqual(correction.actor_id,self.users['staff'].pk)
        self.assertEqual(self.original.amount_cents,20000)
        balances=reconcile(dealership_id=self.dealer.pk,book_id=self.book.pk)
        self.assertEqual(balances['net_debit']['principal'],100000);self.assertEqual(balances['net_debit']['unapplied'],0);self.assertTrue(balances['balanced'])
        receipt=self.client.get(result.url);self.assertContains(receipt,f'Linked reversal #{correction.pk}')
        self.assertContains(receipt,self.data['reference']);self.assertNotContains(receipt,'>Reverse payment<')
        self.assertEqual(self.confirm(response.context['token']).url,result.url)
        self.assertEqual(self.preview().url,result.url)
        self.assertEqual(self.book.postings.filter(kind='reversal').count(),1)
        self.assertEqual(self.preview(reference='Different facts').status_code,409)

    def test_remaining_receipts_are_replayed_and_only_net_coverage_loss_is_shown(self):
        self.record(amount='150.00',effective_on=date(2026,2,5))
        impact=self.preview().context['payment_impact']
        self.assertEqual(impact['after']['amount_due_cents'],5000)
        self.assertEqual(impact['coverage'],[{'number':2,'due_on':'2026-03-01','amount':'$50.00'},{'number':3,'due_on':'2026-04-01','amount':'$100.00'},{'number':4,'due_on':'2026-05-01','amount':'$50.00'}])

    def test_excess_removal_can_leave_due_and_coverage_unchanged(self):
        self.record(amount='1100.00',effective_on=date(2026,2,5))
        response=self.preview();impact=response.context['payment_impact']
        self.assertEqual(impact['coverage'],[]);self.assertEqual(impact['after']['status'],'covered')
        self.assertTrue(impact['excess_changed'])
        self.assertEqual((impact['before']['excess_cents'],impact['after']['excess_cents']),(30000,10000))
        self.assertContains(response,'No net installment coverage is removed')

    def test_account_change_requires_updated_review_and_keeps_reason(self):
        first=self.preview();self.record(amount='50.00')
        stale=self.confirm(first.context['token']);self.assertEqual(stale.status_code,409)
        self.assertContains(stale,'No posting was saved',status_code=409)
        self.assertEqual(stale.context['payment_impact']['after']['amount_due_cents'],15000)
        self.assertFalse(self.book.postings.filter(kind='reversal').exists())
        self.assertContains(stale,self.data['reference'],status_code=409)
        self.assertEqual(self.confirm(stale.context['token']).status_code,302)
        self.assertEqual(self.book.postings.filter(kind='reversal').count(),1)

    def test_edit_and_validation_preserve_work_and_block_already_reversed_payment(self):
        invalid=self.preview(reference='');self.assertContains(invalid,'This field is required.')
        self.assertEqual(invalid.context['form']['request_key'].value(),self.data['request_key'])
        invalid=self.preview(effective_on='2026-01-01');self.assertContains(invalid,'cannot precede')
        preview=self.preview();edit=self.confirm(preview.context['token'],'edit')
        self.assertEqual(edit.context['form']['reference'].value(),self.data['reference'])
        self.assertContains(edit,f'action="{self.url}"')
        self.confirm(preview.context['token'])
        again=self.preview(request_key=str(uuid4()));self.assertContains(again,'already has a reversal')
        self.assertEqual(self.book.postings.filter(kind='reversal').count(),1)

    def test_competing_reversal_is_rejected_and_never_simulated_twice(self):
        first=self.preview()
        reverse_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,posting_id=self.original.pk,actor=self.users['staff'],effective_on=date(2026,3,1),reason='Other invented correction',request_key=uuid4())
        stale=self.confirm(first.context['token']);self.assertEqual(stale.status_code,409)
        self.assertContains(stale,'already has a reversal',status_code=409)
        self.assertEqual(self.book.postings.filter(kind='reversal').count(),1)

    def test_permissions_csrf_tampered_token_and_disabled_simulation(self):
        self.client.force_login(self.users['viewer']);self.assertEqual(self.preview().status_code,403)
        self.client.force_login(self.users['foreign']);self.assertEqual(self.preview().status_code,404)
        self.client.force_login(self.users['staff']);self.assertEqual(self.confirm('invalid').status_code,400)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.users['staff']);self.assertEqual(strict.post(self.url,self.data).status_code,403)
        with override_settings(DEMO_SERVICING_ENABLED=False):
            response=self.preview();self.assertIsNone(response.context['payment_impact'])
            self.assertEqual(self.confirm(response.context['token']).status_code,302)

    def test_unselected_baseline_has_linked_review_without_invented_status(self):
        from .services import open_book
        other,_=open_book(dealership_id=self.dealer.pk,customer_id=self.book.customer_id,actor=self.users['staff'],label='Invented unselected account',source_reference='Synthetic only',opening_on=date(2026,1,1),opening_amount='1000',request_key=uuid4())
        original,_=record_receipt(dealership_id=self.dealer.pk,book_id=other.pk,actor=self.users['staff'],amount='50',effective_on=date(2026,2,1),reason='Invented unselected payment',request_key=uuid4())
        url=reverse('ledger_demo_reverse',args=[other.pk,original.pk])
        response=self.client.post(url,self.data)
        self.assertIsNone(response.context['payment_impact']);self.assertContains(response,f'Original receipt #{original.pk}')
        self.assertNotContains(response,'Demo reversal impact');self.assertEqual(self.confirm(response.context['token']).status_code,302)

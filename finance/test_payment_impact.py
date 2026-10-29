# SPDX-License-Identifier: MPL-2.0
from datetime import date
from uuid import uuid4
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.urls import reverse
from . import test_servicing as references
from .servicing_services import select_baseline
from .services import record_receipt,reconcile
from .models import DemoServicingPlan


@override_settings(DEMO_LEDGER_ENABLED=True,DEMO_SERVICING_ENABLED=True)
class PaymentImpactTests(TestCase):
    @classmethod
    def setUpTestData(cls):references.ServicingIntegrationTests.setUpTestData.__func__(cls)
    def setUp(self):
        self.client.force_login(self.users['staff'])
        clock=patch('finance.servicing_services.timezone.localdate',return_value=date(2026,3,2));clock.start();self.addCleanup(clock.stop)
        self.data={'amount':'150.00','effective_on':'2026-02-01','reference':'Invented payment impact','request_key':str(uuid4()),'synthetic_confirmed':'on'}
        self.url=reverse('ledger_demo_receipt',args=[self.book.pk]);self.confirm_url=reverse('ledger_demo_confirm')
    def select(self):
        select_baseline(dealership_id=self.dealer.pk,book_id=self.book.pk,schedule_id=self.schedule.pk,actor=self.users['staff'],reason='Synthetic impact baseline',creation_key=uuid4(),expected_digest=self.schedule.result_sha256)
    def preview(self,**extra):return self.client.post(self.url,{**self.data,**extra})
    def confirm(self,token):return self.client.post(self.confirm_url,{'preview_token':token,'action':'post'})
    def record(self,amount='50.00',effective_on=date(2026,2,5)):
        return record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.users['staff'],amount=amount,effective_on=effective_on,reason='Invented concurrent receipt',request_key=uuid4())[0]

    def test_before_after_and_installments_are_independent_reference_values(self):
        self.select();before=reconcile(dealership_id=self.dealer.pk,book_id=self.book.pk)
        response=self.preview();impact=response.context['payment_impact']
        self.assertEqual(impact['before']['amount_due_cents'],20000)
        self.assertEqual(impact['after']['amount_due_cents'],5000)
        self.assertEqual(impact['before']['days_past_due'],29)
        self.assertEqual(impact['after']['days_past_due'],1)
        self.assertEqual(impact['coverage'],[{'number':1,'due_on':'2026-02-01','amount':'$100.00'},{'number':2,'due_on':'2026-03-01','amount':'$50.00'}])
        self.assertContains(response,'Demo payment impact')
        self.assertEqual(before,reconcile(dealership_id=self.dealer.pk,book_id=self.book.pk))
        saved=self.confirm(response.context['token']);self.assertEqual(saved.status_code,302)
        after=reconcile(dealership_id=self.dealer.pk,book_id=self.book.pk)
        self.assertEqual(after['net_debit']['principal'],100000)
        self.assertEqual(after['net_debit']['unapplied'],-15000)

    def test_excess_and_long_coverage_have_full_details_available(self):
        self.select();response=self.preview(amount='1100.00');impact=response.context['payment_impact']
        self.assertEqual(impact['after']['status'],'covered')
        self.assertEqual(impact['excess'],'$100.00')
        self.assertEqual(len(impact['shown_coverage']),5);self.assertEqual(len(impact['more_coverage']),5)
        self.assertContains(response,'View all 10 covered installments')
        self.assertFalse(self.book.postings.filter(kind='receipt').exists())

    def test_backdating_explains_redistribution_without_rewriting_receipts(self):
        self.select();original=self.record(amount='150.00',effective_on=date(2026,3,1))
        response=self.preview(amount='100.00');impact=response.context['payment_impact']
        self.assertTrue(impact['redistributed'])
        self.assertEqual(impact['coverage'],[{'number':1,'due_on':'2026-02-01','amount':'$100.00'}])
        self.assertEqual(impact['after']['amount_due_cents'],0)
        self.assertContains(response,'backdated payment redistributes')
        original.refresh_from_db();self.assertEqual(original.amount_cents,15000)
        self.assertEqual(self.book.postings.filter(kind='receipt').count(),1)

    def test_account_change_requires_fresh_review_then_posts_once(self):
        self.select();response=self.preview();token=response.context['token'];self.record()
        changed=self.confirm(token)
        self.assertEqual(changed.status_code,409)
        self.assertContains(changed,'This account changed',status_code=409)
        self.assertTrue(changed.context['impact_changed'])
        self.assertEqual(changed.context['payment_impact']['before']['amount_due_cents'],15000)
        self.assertEqual(changed.context['payment_impact']['after']['amount_due_cents'],0)
        self.assertEqual(self.book.postings.filter(kind='receipt').count(),1)
        saved=self.confirm(changed.context['token']);self.assertEqual(saved.status_code,302)
        self.record(amount='5.00')
        self.assertEqual(self.confirm(token).url,saved.url)
        self.assertEqual(self.book.postings.filter(kind='receipt').count(),3)

    def test_selecting_baseline_after_preview_forces_new_review(self):
        response=self.preview();self.assertIsNone(response.context['payment_impact'])
        self.select();changed=self.confirm(response.context['token'])
        self.assertEqual(changed.status_code,409);self.assertIsNotNone(changed.context['payment_impact'])
        self.assertFalse(self.book.postings.filter(kind='receipt').exists())

    def test_edit_preserves_fields_and_recorded_retry_cannot_double_preview(self):
        self.select();preview=self.preview();token=preview.context['token']
        edited=self.client.post(self.confirm_url,{'preview_token':token,'action':'edit'})
        self.assertEqual(edited.context['form']['amount'].value(),'150.00')
        self.assertEqual(str(edited.context['form']['request_key'].value()),self.data['request_key'])
        saved=self.confirm(token)
        repeated=self.preview();self.assertEqual(repeated.status_code,302);self.assertEqual(repeated.url,saved.url)
        conflict=self.preview(amount='151.00');self.assertEqual(conflict.status_code,409)
        self.assertEqual(self.book.postings.filter(kind='receipt').count(),1)

    def test_unselected_or_disabled_simulation_keeps_ordinary_review(self):
        response=self.preview();self.assertIsNone(response.context['payment_impact'])
        self.assertNotContains(response,'Demo payment impact')
        self.select()
        with override_settings(DEMO_SERVICING_ENABLED=False):
            response=self.preview();self.assertIsNone(response.context['payment_impact'])
            self.assertEqual(self.confirm(response.context['token']).status_code,302)

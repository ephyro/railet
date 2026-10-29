# SPDX-License-Identifier: MPL-2.0
from datetime import date
from uuid import uuid4
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.urls import reverse
from . import test_accounts as fixtures
from .models import DemoPosting,DemoAccountExport
from .services import record_receipt,reverse_receipt
from .account_services import link_draft
from .schedule_services import result_digest
from deals.account_context import account_draft_snapshot


@override_settings(DEMO_LEDGER_ENABLED=True)
class PrintableReceiptTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.AccountWorkspaceTests.setUpTestData.__func__(cls)
        link_draft(dealership_id=cls.dealer.pk,book_id=cls.book.pk,deal_id=cls.deal.pk,actor=cls.users['staff'],expected_digest=result_digest(account_draft_snapshot(cls.deal)))
        cls.posting,_=record_receipt(dealership_id=cls.dealer.pk,book_id=cls.book.pk,actor=cls.users['staff'],amount='125.50',payment_method='check',effective_on=date(2026,2,1),reason='Invented print reference <script>unsafe()</script>',request_key=uuid4())
    def setUp(self):
        self.client.force_login(self.users['staff']);self.url=reverse('bhph_account_receipt',args=[self.book.pk,self.posting.pk])

    def test_exact_print_facts_and_frozen_vehicle_context_are_read_only(self):
        before=list(DemoPosting.objects.values());exports=DemoAccountExport.objects.count()
        self.vehicle.model='Changed current vehicle';self.vehicle.stock_number='CHANGED-CURRENT';self.vehicle.save()
        response=self.client.get(self.url)
        for value in ('$125.50','Check','Feb 1, 2026','2020 Synthetic Sedan','DEMO-ACCOUNT','As saved when linked','Customer (current profile)','Unapplied','Print receipt','Demonstration only','User #'):
            self.assertContains(response,value)
        self.assertNotContains(response,'Changed current vehicle');self.assertNotContains(response,'CHANGED-CURRENT')
        self.assertContains(response,'&lt;script&gt;unsafe()&lt;/script&gt;');self.assertNotContains(response,'<script>unsafe()</script>')
        self.assertIsNotNone(response.context['captured_at']);self.assertEqual(response.context['display_zone'],'America/New_York')
        self.assertEqual(list(DemoPosting.objects.values()),before);self.assertEqual(DemoAccountExport.objects.count(),exports)
        self.assertIn('no-store',response['Cache-Control']);self.assertEqual(response['X-Content-Type-Options'],'nosniff')

    def test_reversed_receipt_keeps_original_and_full_correction_evidence(self):
        reversal,_=reverse_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,posting_id=self.posting.pk,actor=self.users['staff'],effective_on=date(2026,2,2),reason='Invented print correction',request_key=uuid4())
        response=self.client.get(self.url)
        for value in ('Reversed in full',f'Linked reversal #{reversal.pk}','Invented print correction','Feb 2, 2026','$125.50','not a refund'):
            self.assertContains(response,value)
        self.assertNotContains(response,'>Reverse payment<');self.assertContains(response,'Print receipt')
        self.posting.refresh_from_db();self.assertEqual(self.posting.amount_cents,12550)
        self.assertEqual(reversal.reverses_id,self.posting.pk)

    def test_current_customer_identity_is_labeled_and_not_claimed_as_historical_snapshot(self):
        self.customer.first_name='Updated Synthetic';self.customer.save()
        response=self.client.get(self.url);self.assertContains(response,'Updated Synthetic Demo')
        self.assertContains(response,'current profile');self.assertContains(response,'not a stored receipt snapshot')
        self.assertEqual(response.context['posting'].pk,self.posting.pk)

    def test_viewer_can_print_but_foreign_and_disabled_access_are_blocked(self):
        self.client.force_login(self.users['viewer']);response=self.client.get(self.url)
        self.assertContains(response,'Print receipt');self.assertNotContains(response,'>Reverse payment<')
        self.client.force_login(self.users['foreign']);self.assertEqual(self.client.get(self.url).status_code,404)
        self.client.force_login(self.users['staff'])
        with override_settings(DEMO_LEDGER_ENABLED=False):self.assertEqual(self.client.get(self.url).status_code,403)
        self.assertEqual(self.client.post(self.url).status_code,405)

    def test_invalid_vehicle_context_does_not_print_unverified_facts(self):
        with patch('finance.account_views.result_digest',return_value='invalid'):
            response=self.client.get(self.url)
        self.assertEqual(response.status_code,409);self.assertContains(response,'could not be verified',status_code=409)
        self.assertNotContains(response,'Print receipt',status_code=409)

# SPDX-License-Identifier: MPL-2.0
from datetime import date
from decimal import Decimal
from uuid import uuid4
from django.test import TestCase, override_settings
from django.urls import reverse
from deals import test_completion as reference
from deals.models import DraftFinanceProposal
from deals.completion import complete
from deals.account_context import completed_account_snapshot
from finance.account_services import open_from_draft
from finance.models import DemoBook, DemoPosting, DemoAccountContext
from finance.schedule_services import result_digest
from finance.services import LedgerError


@override_settings(DEMO_LEDGER_ENABLED=True, DEMO_COMPLETION_ENABLED=True, DEMO_PACKETS_ENABLED=True)
class CompletedHandoffTests(TestCase):
    def setUp(self):
        reference.CompletionTests.setUp(self)
        self.deal.deal_type='bhph';self.deal.save()
        DraftFinanceProposal.objects.create(deal=self.deal,kind='bhph',interest_method='precomputed',creditor_name='Practice creditor',payment_frequency='monthly',payment_count=12,annual_contract_rate=Decimal('0'),first_payment_date=date(2026,12,1),illustration_finance_charge=Decimal('200'))
        complete(**reference.CompletionTests.args(self))

    def source(self):
        from deals.completion import preview
        return preview(dealership_id=self.dealer.pk, deal_id=self.deal.pk)

    def test_frozen_parties_terms_and_balanced_idempotent_opening(self):
        self.buyer.first_name='Changed';self.buyer.save()
        self.vehicle.model='Changed';self.vehicle.save()
        self.deal.refresh_from_db()
        snapshot=completed_account_snapshot(self.deal)
        self.assertEqual(snapshot['customer_name'],'Practice Buyer')
        self.assertEqual(snapshot['vehicle'],'2021 Synthetic Review Sedan')
        self.assertEqual(snapshot['proposed_terms']['illustration_finance_charge'],'200.00')
        args=dict(dealership_id=self.dealer.pk,deal_id=self.deal.pk,actor=self.user,opening_amount='1000.25',opening_on=date(2026,11,1),source_reference='Invented opening',request_key=uuid4(),expected_digest=result_digest(snapshot))
        book,created=open_from_draft(**args)
        self.assertTrue(created);self.assertEqual(open_from_draft(**args)[0].pk,book.pk)
        context=DemoAccountContext.objects.get(book=book)
        self.assertEqual(result_digest(context.snapshot),result_digest(snapshot))
        posting=DemoPosting.objects.get(book=book)
        self.assertEqual((posting.amount_cents,posting.debit,posting.credit),(100025,'principal','opening_offset'))
        self.assertEqual(DemoBook.objects.count(),1)
        from finance.services import record_receipt
        receipt,_=record_receipt(dealership_id=self.dealer.pk,book_id=book.pk,actor=self.user,amount='75.50',effective_on=date(2026,11,1),reason='Invented test payment',request_key=uuid4())
        self.assertEqual(receipt.amount_cents,7550)
        response=self.client.get(reverse('bhph_account',args=[book.pk]))
        self.assertContains(response,'Name at completion: Practice Buyer')
        self.assertContains(response,'Changed')
        self.assertEqual(self.client.get(reverse('draft_demo_account',args=[self.deal.pk])).status_code,302)

    def test_changed_digest_is_rejected_without_opening(self):
        with self.assertRaises(LedgerError):
            open_from_draft(dealership_id=self.dealer.pk,deal_id=self.deal.pk,actor=self.user,opening_amount='1000',opening_on=date(2026,11,1),source_reference='Invented',request_key=uuid4(),expected_digest='0'*64)
        self.assertFalse(DemoBook.objects.exists())

    def test_http_review_uses_frozen_names_and_creates_once(self):
        self.buyer.first_name='Changed';self.buyer.save()
        self.vehicle.model='Changed';self.vehicle.save()
        route=reverse('draft_demo_account',args=[self.deal.pk])
        response=self.client.get(route)
        self.assertContains(response,'Practice Buyer');self.assertContains(response,'Review Sedan')
        self.assertNotContains(response,'Changed')
        data={'amount':'1250.50','effective_on':'2026-10-30','reference':'Synthetic opening','request_key':str(uuid4()),'synthetic_confirmed':'on'}
        response=self.client.post(route,data)
        self.assertContains(response,'Practice Buyer');self.assertContains(response,'Review Sedan')
        token=response.context['token']
        response=self.client.post(route,{'preview_token':token,'action':'open'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.post(route,{'preview_token':token,'action':'open'}).status_code,302)
        self.assertEqual(DemoBook.objects.count(),1)

    def test_existing_viewer_cannot_open_account(self):
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.client.get(reverse('draft_demo_account',args=[self.deal.pk])).status_code,403)
        self.assertFalse(DemoBook.objects.exists())

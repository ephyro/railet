# SPDX-License-Identifier: MPL-2.0
from datetime import date
from uuid import uuid4
from unittest import skipUnless
from django.db import connection
from django.test import Client,TransactionTestCase,override_settings
from django.urls import reverse
from . import test_servicing as references
from . import test_concurrency as concurrency
from .servicing_services import select_baseline
from .services import record_receipt

@skipUnless(connection.vendor=='postgresql','Reversal review concurrency requires PostgreSQL')
@override_settings(DEMO_LEDGER_ENABLED=True,DEMO_SERVICING_ENABLED=True)
class ReversalImpactConcurrencyTests(TransactionTestCase):
    def setUp(self):
        references.ServicingIntegrationTests.setUpTestData.__func__(type(self))
        select_baseline(dealership_id=self.dealer.pk,book_id=self.book.pk,schedule_id=self.schedule.pk,actor=self.users['staff'],reason='Synthetic reversal review',creation_key=uuid4(),expected_digest=self.schedule.result_sha256)
        self.original,_=record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.users['staff'],amount='200.00',effective_on=date(2026,2,1),reason='Synthetic original',request_key=uuid4())
        self.client.force_login(self.users['staff'])
    def preview(self):
        return self.client.post(reverse('ledger_demo_reverse',args=[self.book.pk,self.original.pk]),{'effective_on':'2026-03-02','reference':'Synthetic reversal race','request_key':str(uuid4()),'synthetic_confirmed':'on'}).context['token']
    def post(self,token):
        client=Client();client.force_login(self.users['staff'])
        response=client.post(reverse('ledger_demo_confirm'),{'preview_token':token,'action':'post'})
        return response.status_code,response.get('Location')
    def test_same_preview_posts_one_linked_reversal(self):
        token=self.preview();results=concurrency.LedgerConcurrencyTests.race(self,[lambda:self.post(token),lambda:self.post(token)])
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0][0],302)
        self.assertEqual(self.book.postings.filter(kind='reversal',reverses=self.original).count(),1)
    def test_competing_previews_cannot_reverse_same_payment_twice(self):
        first=self.preview();second=self.preview();results=concurrency.LedgerConcurrencyTests.race(self,[lambda:self.post(first),lambda:self.post(second)])
        self.assertCountEqual([code for code,_ in results],[302,409]);self.assertEqual(self.book.postings.filter(kind='reversal').count(),1)

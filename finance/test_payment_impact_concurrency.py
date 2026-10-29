# SPDX-License-Identifier: MPL-2.0
from unittest import skipUnless
from uuid import uuid4
from django.db import connection
from django.test import Client,TransactionTestCase,override_settings
from django.urls import reverse
from . import test_servicing as references
from . import test_concurrency as concurrency
from .servicing_services import select_baseline

@skipUnless(connection.vendor=='postgresql','Payment review concurrency requires PostgreSQL')
@override_settings(DEMO_LEDGER_ENABLED=True,DEMO_SERVICING_ENABLED=True)
class PaymentImpactConcurrencyTests(TransactionTestCase):
    def setUp(self):
        references.ServicingIntegrationTests.setUpTestData.__func__(type(self))
        select_baseline(dealership_id=self.dealer.pk,book_id=self.book.pk,schedule_id=self.schedule.pk,actor=self.users['staff'],reason='Synthetic concurrent review baseline',creation_key=uuid4(),expected_digest=self.schedule.result_sha256)
        self.client.force_login(self.users['staff'])
    def preview(self):
        response=self.client.post(reverse('ledger_demo_receipt',args=[self.book.pk]),{'amount':'150.00','effective_on':'2026-02-01','reference':'Synthetic concurrent review','request_key':str(uuid4()),'synthetic_confirmed':'on'})
        return response.context['token']
    def post(self,token):
        client=Client();client.force_login(self.users['staff'])
        response=client.post(reverse('ledger_demo_confirm'),{'preview_token':token,'action':'post'})
        return response.status_code,response.get('Location')
    def test_same_preview_commits_one_receipt(self):
        token=self.preview()
        results=concurrency.LedgerConcurrencyTests.race(self,[lambda:self.post(token),lambda:self.post(token)])
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0][0],302)
        self.assertEqual(self.book.postings.filter(kind='receipt').count(),1)
    def test_distinct_previews_cannot_post_stale_consequences(self):
        first=self.preview();second=self.preview()
        results=concurrency.LedgerConcurrencyTests.race(self,[lambda:self.post(first),lambda:self.post(second)])
        self.assertCountEqual([code for code,_ in results],[302,409])
        self.assertEqual(self.book.postings.filter(kind='receipt').count(),1)

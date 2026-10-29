# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import date
from uuid import uuid4
from unittest import skipUnless
from django.db import connection, close_old_connections
from django.test import TransactionTestCase, override_settings
from django.contrib.auth import get_user_model
from deals.account_context import account_draft_snapshot
from . import test_accounts as account_fixtures
from .account_services import open_from_draft
from .schedule_services import result_digest
from .models import DemoAccountContext, DemoBook
from .services import LedgerError


@skipUnless(connection.vendor=='postgresql','PostgreSQL row locks required')
@override_settings(DEMO_LEDGER_ENABLED=True)
class DraftAccountConcurrencyTests(TransactionTestCase):
    def setUp(self):
        account_fixtures.AccountWorkspaceTests.setUpTestData.__func__(type(self))
        self.fingerprint=result_digest(account_draft_snapshot(self.deal))

    def race(self,keys):
        barrier=Barrier(2)
        def run(key):
            close_old_connections()
            try:
                actor=get_user_model().objects.get(pk=self.users['staff'].pk)
                barrier.wait(timeout=10)
                try:
                    book,created=open_from_draft(dealership_id=self.dealer.pk,deal_id=self.deal.pk,
                        actor=actor,opening_amount='1200.25',opening_on=date(2026,1,1),
                        source_reference='Synthetic concurrent opening',request_key=key,expected_digest=self.fingerprint)
                    return book.pk,created
                except LedgerError:return 'duplicate'
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(run,keys))

    def test_same_preview_can_create_only_one_opening(self):
        key=uuid4();results=self.race([key,key])
        self.assertEqual(results[0][0],results[1][0])
        self.assertEqual(sorted(item[1] for item in results),[False,True])
        self.assertEqual(DemoAccountContext.objects.count(),1)
        self.assertEqual(DemoBook.objects.count(),2)  # Existing unlinked fixture + new account.

    def test_distinct_previews_for_same_draft_cannot_create_two_accounts(self):
        results=self.race([uuid4(),uuid4()])
        self.assertEqual(results.count('duplicate'),1)
        self.assertEqual(DemoAccountContext.objects.count(),1)
        self.assertEqual(DemoBook.objects.count(),2)

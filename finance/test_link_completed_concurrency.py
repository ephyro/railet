# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from deals.account_context import completed_account_snapshot
from . import test_completed_handoff as handoff
from .account_services import link_completed
from .models import DemoAccountContext
from .schedule_services import result_digest
from .services import LedgerError, open_book


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL row locks required')
@override_settings(DEMO_LEDGER_ENABLED=True, DEMO_COMPLETION_ENABLED=True, DEMO_PACKETS_ENABLED=True)
class LinkCompletedConcurrencyTests(TransactionTestCase):
    source = handoff.CompletedHandoffTests.source

    def setUp(self):
        handoff.CompletedHandoffTests.setUp(self)
        self.books = []
        for number in range(2):
            book, _ = open_book(dealership_id=self.dealer.pk, customer_id=self.buyer.pk, actor=self.user,
                label=f'Synthetic {number}', source_reference='Invented', opening_on=date(2026, 1, 1),
                opening_amount='50', request_key=uuid4())
            self.books.append(book)
        self.digest = result_digest(completed_account_snapshot(self.deal))

    def race(self, ids):
        barrier = Barrier(2)
        def run(book_id):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=self.user.pk)
                barrier.wait(timeout=10)
                try:
                    return link_completed(dealership_id=self.dealer.pk, book_id=book_id, deal_id=self.deal.pk,
                                          actor=actor, expected_digest=self.digest).pk
                except LedgerError:
                    return 'conflict'
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, ids))

    def test_same_preview_retries_create_one_context(self):
        results = self.race([self.books[0].pk, self.books[0].pk])
        self.assertEqual(results[0], results[1])
        self.assertNotEqual(results[0], 'conflict')
        self.assertEqual(DemoAccountContext.objects.count(), 1)

    def test_competing_accounts_cannot_claim_same_completion(self):
        results = self.race([book.pk for book in self.books])
        self.assertEqual(results.count('conflict'), 1)
        self.assertEqual(DemoAccountContext.objects.count(), 1)

    def test_deactivation_while_waiting_prevents_completed_link(self):
        from threading import Event
        from django.core.exceptions import PermissionDenied
        from django.db import transaction
        from core.models import Dealership
        started=Event()
        def invoke():
            close_old_connections()
            try:
                started.set()
                try:
                    link_completed(dealership_id=self.dealer.pk,book_id=self.books[0].pk,
                        deal_id=self.deal.pk,actor=self.user,expected_digest=self.digest)
                except PermissionDenied: return 'denied'
                return 'allowed'
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Dealership.objects.select_for_update().get(pk=self.dealer.pk)
                future=pool.submit(invoke)
                self.assertTrue(started.wait(10))
                get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
            self.assertEqual(future.result(timeout=15),'denied')
        self.assertFalse(DemoAccountContext.objects.exists())

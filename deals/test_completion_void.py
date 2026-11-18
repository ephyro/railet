# SPDX-License-Identifier: MPL-2.0
from datetime import date
from threading import Barrier, Thread
from uuid import uuid4
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from finance import test_completed_handoff as fixture
from finance.account_services import link_completed, open_from_draft
from finance.models import DemoAccountContext, DemoBook, DemoPosting
from finance.schedule_services import result_digest
from finance.services import LedgerError, open_book
from .account_context import completed_account_snapshot
from .completion import CompletionChanged, preview_void, void_completion
from .models import DemoCompletionVoid


@override_settings(DEBUG=True, DEMO_LEDGER_ENABLED=True, DEMO_COMPLETION_ENABLED=True, DEMO_PACKETS_ENABLED=True)
class VoidTests(TestCase):
    source = fixture.CompletedHandoffTests.source
    def setUp(self):
        fixture.CompletedHandoffTests.setUp(self)
        self.record = self.deal.demo_completion
        self.digest = preview_void(dealership_id=self.dealer.pk, deal_id=self.deal.pk, actor=self.user)[1]
        self.account_digest = result_digest(completed_account_snapshot(self.deal))
        self.args = dict(dealership_id=self.dealer.pk, deal_id=self.deal.pk, actor=self.user,
                         creation_key=uuid4(), expected_review=self.digest, reason='Synthetic mistake')

    def open_args(self):
        return dict(dealership_id=self.dealer.pk, deal_id=self.deal.pk, actor=self.user,
                    opening_amount='1000', opening_on=date(2026, 11, 1), source_reference='Synthetic',
                    request_key=uuid4(), expected_digest=self.account_digest)

    def test_immutable_retry_and_original_retained_and_exported(self):
        packet = self.record.packet
        before = (packet.html, packet.snapshot, self.record.review_sha256)
        void = void_completion(**self.args)
        self.assertEqual(void.pk, void_completion(**self.args).pk)
        with self.assertRaises(CompletionChanged): void_completion(**(self.args | {'creation_key': uuid4()}))
        for operation in (lambda: DemoCompletionVoid.objects.filter(pk=void.pk).update(reason='changed'),
                          lambda: DemoCompletionVoid.objects.filter(pk=void.pk).delete()):
            with self.assertRaises(DatabaseError), transaction.atomic(): operation()
        self.record.refresh_from_db(); packet.refresh_from_db()
        self.assertEqual((packet.html, packet.snapshot, self.record.review_sha256), before)
        self.assertFalse(DemoBook.objects.exists())
        response = self.client.get(reverse('deal_completion', args=[self.deal.pk]))
        self.assertContains(response, 'Synthetic mistake'); self.assertNotContains(response, 'Set up demo BHPH account')
        from core.models import Membership
        Membership.objects.filter(user=self.user).update(role='owner')
        from .export import export_deals
        data = export_deals(dealership_id=self.dealer.pk, actor=self.user)
        self.assertEqual(data['completion_void_rehearsals'][0]['reason'], 'Synthetic mistake')

    def test_void_blocks_both_opening_and_existing_account_link(self):
        book, _ = open_book(dealership_id=self.dealer.pk, customer_id=self.buyer.pk, actor=self.user,
            label='Synthetic', source_reference='Synthetic', opening_on=date(2026, 1, 1), opening_amount='10', request_key=uuid4())
        before = list(DemoPosting.objects.filter(book=book).values())
        void_completion(**self.args)
        with self.assertRaises(LedgerError): open_from_draft(**self.open_args())
        with self.assertRaises(LedgerError): link_completed(dealership_id=self.dealer.pk, book_id=book.pk,
            deal_id=self.deal.pk, actor=self.user, expected_digest=self.account_digest)
        self.assertEqual(list(DemoPosting.objects.filter(book=book).values()), before)
        self.assertFalse(DemoAccountContext.objects.exists())

    def test_linked_account_blocks_void_even_if_ledger_disabled(self):
        open_from_draft(**self.open_args())
        before = list(DemoPosting.objects.values())
        with override_settings(DEMO_LEDGER_ENABLED=False), self.assertRaises(CompletionChanged): void_completion(**self.args)
        self.assertEqual(list(DemoPosting.objects.values()), before)
        self.assertFalse(DemoCompletionVoid.objects.exists())
        response = self.client.get(reverse('deal_completion_void', args=[self.deal.pk]))
        self.assertEqual(response.status_code, 409)

    def test_stale_authorization_and_http(self):
        with self.assertRaises(CompletionChanged): void_completion(**(self.args | {'expected_review': '0'*64}))
        with self.assertRaises(CompletionChanged): void_completion(**(self.args | {'reason': '  '}))
        with self.assertRaises(PermissionDenied): void_completion(**(self.args | {'actor': self.users['viewer']}))
        url = reverse('deal_completion_void', args=[self.deal.pk])
        self.client.force_login(self.users['foreign']); self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.users['viewer']); self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.user)
        response = self.client.get(url); self.assertEqual(response.status_code, 200)
        token = response.context['form']['preview_token'].value()
        self.assertEqual(self.client.post(url, {'preview_token': token+'x', 'reason':'Synthetic', 'confirmed':'on'}).status_code, 400)
        post = {'preview_token': token, 'reason':'Synthetic', 'confirmed':'on'}
        self.assertEqual(self.client.post(url, post).status_code, 302)
        self.assertEqual(self.client.post(url, post).status_code, 302)
        self.assertEqual(self.client.post(url, post | {'reason': 'different'}).status_code, 409)
        with override_settings(DEMO_COMPLETION_ENABLED=False): self.assertEqual(self.client.get(url).status_code, 404)


@override_settings(DEBUG=True, DEMO_LEDGER_ENABLED=True, DEMO_COMPLETION_ENABLED=True, DEMO_PACKETS_ENABLED=True)
class VoidConcurrencyTests(TransactionTestCase):
    source = fixture.CompletedHandoffTests.source
    def race(self, mode):
        fixture.CompletedHandoffTests.setUp(self)
        book = None
        if mode == 'link':
            book, _ = open_book(dealership_id=self.dealer.pk, customer_id=self.buyer.pk, actor=self.user, label='Synthetic', source_reference='Synthetic', opening_on=date(2026,1,1), opening_amount='10', request_key=uuid4())
        vdigest = preview_void(dealership_id=self.dealer.pk, deal_id=self.deal.pk, actor=self.user)[1]
        adigest = result_digest(completed_account_snapshot(self.deal))
        barrier = Barrier(2); outcomes = []
        def run(kind):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                if kind == 'void':
                    void_completion(dealership_id=self.dealer.pk, deal_id=self.deal.pk, actor=self.user,
                        creation_key=uuid4(), expected_review=vdigest, reason='Synthetic')
                elif mode == 'link':
                    link_completed(dealership_id=self.dealer.pk, book_id=book.pk, deal_id=self.deal.pk, actor=self.user, expected_digest=adigest)
                else:
                    open_from_draft(dealership_id=self.dealer.pk, deal_id=self.deal.pk, actor=self.user,
                        opening_amount='10', opening_on=date(2026,11,1), source_reference='Synthetic',
                        request_key=uuid4(), expected_digest=adigest)
                outcomes.append((kind, 'ok'))
            except (CompletionChanged, LedgerError): outcomes.append((kind, 'conflict'))
            finally: close_old_connections()
        threads = [Thread(target=run,args=(kind,)) for kind in ('void','open')]
        for thread in threads: thread.start()
        for thread in threads: thread.join(20)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(sorted(value for _,value in outcomes), ['conflict','ok'])
        self.assertNotEqual(DemoCompletionVoid.objects.exists(), DemoAccountContext.objects.exists())

    @skipUnlessDBFeature('has_select_for_update')
    def test_void_and_open_are_serialized(self):
        self.race('open')

    @skipUnlessDBFeature('has_select_for_update')
    def test_void_and_link_are_serialized(self):
        self.race('link')

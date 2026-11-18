# SPDX-License-Identifier: MPL-2.0
from datetime import date
from unittest.mock import patch
from uuid import uuid4
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase, override_settings
from django.urls import reverse
from customers.models import Customer
from deals.account_context import completed_account_snapshot
from . import test_completed_handoff as handoff
from .account_services import link_completed
from .models import DemoAccountContext, DemoPosting
from .schedule_services import result_digest
from .services import LedgerError, open_book, record_receipt, reconcile


@override_settings(DEMO_LEDGER_ENABLED=True, DEMO_COMPLETION_ENABLED=True, DEMO_PACKETS_ENABLED=True)
class LinkCompletedTests(TestCase):
    source = handoff.CompletedHandoffTests.source

    def setUp(self):
        handoff.CompletedHandoffTests.setUp(self)
        self.book, _ = open_book(dealership_id=self.dealer.pk, customer_id=self.buyer.pk, actor=self.user,
            label='Existing synthetic account', source_reference='Invented', opening_on=date(2026, 1, 1),
            opening_amount='900', request_key=uuid4())
        record_receipt(dealership_id=self.dealer.pk, book_id=self.book.pk, actor=self.user,
            amount='25', effective_on=date(2026, 1, 2), reason='Synthetic receipt', request_key=uuid4())
        self.url = reverse('bhph_account_link', args=[self.book.pk])
        self.digest = result_digest(completed_account_snapshot(self.deal))

    def link_args(self, **kwargs):
        return dict(dealership_id=self.dealer.pk, book_id=self.book.pk, deal_id=self.deal.pk,
                    actor=self.user, expected_digest=self.digest) | kwargs

    def test_explicit_preview_retry_preserves_frozen_identity_and_ledger(self):
        before = reconcile(dealership_id=self.dealer.pk, book_id=self.book.pk)
        self.buyer.first_name = 'Current'; self.buyer.save()
        self.vehicle.model = 'Current'; self.vehicle.save()
        response = self.client.post(self.url, {'deal': self.deal.pk})
        self.assertContains(response, 'Practice Buyer')
        self.assertContains(response, 'Review Sedan')
        self.assertFalse(DemoAccountContext.objects.exists())
        token = response.context['token']
        self.assertEqual(self.client.post(self.url, {'preview_token': token}).status_code, 302)
        self.assertEqual(self.client.post(self.url, {'preview_token': token}).status_code, 302)
        context = DemoAccountContext.objects.get(book=self.book)
        self.assertEqual(context.snapshot['source'], 'completed-rehearsal')
        self.assertEqual(context.snapshot['customer_name'], 'Practice Buyer')
        self.assertEqual(context.snapshot['completion_id'], self.deal.demo_completion.pk)
        self.assertEqual(DemoPosting.objects.filter(book=self.book).count(), 2)
        self.assertEqual(reconcile(dealership_id=self.dealer.pk, book_id=self.book.pk), before)

    def test_mismatched_account_conflicts_and_actor_scope(self):
        other_customer = Customer.objects.create(dealership=self.dealer, first_name='Other synthetic')
        other, _ = open_book(dealership_id=self.dealer.pk, customer_id=other_customer.pk, actor=self.user,
            label='Other', source_reference='Synthetic', opening_on=date(2026, 1, 1), opening_amount='20', request_key=uuid4())
        with self.assertRaises(Http404): link_completed(**self.link_args(book_id=other.pk))
        with self.assertRaises(PermissionDenied): link_completed(**self.link_args(actor=self.users['viewer']))
        with self.assertRaises(Http404): link_completed(**self.link_args(dealership_id=self.other.pk, actor=self.users['foreign']))
        self.assertFalse(DemoAccountContext.objects.exists())
        first = link_completed(**self.link_args())
        self.assertEqual(link_completed(**self.link_args()).pk, first.pk)
        another, _ = open_book(dealership_id=self.dealer.pk, customer_id=self.buyer.pk, actor=self.user,
            label='Another', source_reference='Synthetic', opening_on=date(2026, 1, 1), opening_amount='30', request_key=uuid4())
        with self.assertRaises(LedgerError): link_completed(**self.link_args(book_id=another.pk))
        self.assertEqual(DemoAccountContext.objects.count(), 1)

    def test_tamper_stale_gate_and_token_are_rejected(self):
        with self.assertRaises(LedgerError): link_completed(**self.link_args(expected_digest='0' * 64))
        response = self.client.post(self.url, {'deal': self.deal.pk})
        token = response.context['token']
        self.assertEqual(self.client.post(self.url, {'preview_token': token + 'x'}).status_code, 200)
        with patch('deals.completion.digest', return_value='corrupted'):
            self.assertEqual(self.client.post(self.url, {'preview_token': token}).status_code, 409)
            self.assertEqual(self.client.post(self.url, {'deal': self.deal.pk}).status_code, 409)
        with override_settings(DEMO_COMPLETION_ENABLED=False):
            self.assertEqual(self.client.post(self.url, {'preview_token': token}).status_code, 404)
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.client.post(self.url, {'preview_token': token}).status_code, 403)
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.post(self.url, {'preview_token': token}).status_code, 404)
        self.assertFalse(DemoAccountContext.objects.exists())

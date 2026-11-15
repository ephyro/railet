# SPDX-License-Identifier: MPL-2.0
"""Independent synthetic direct-URL and export authorization checks."""
import io
import json
import zipfile
from datetime import date
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from core.models import Membership
from customers.models import Customer
from . import test_accounts as fixtures
from .models import DemoAccountContext, DemoAccountExport, DemoPosting
from .services import open_book, record_receipt


@override_settings(DEMO_LEDGER_ENABLED=True)
class AccountAccessAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.AccountWorkspaceTests.setUpTestData.__func__(cls)
        cls.owner = get_user_model().objects.create_user('audit-owner')
        Membership.objects.create(user=cls.owner, dealership=cls.dealer, role='owner')
        cls.second_staff = get_user_model().objects.create_user('audit-second-staff')
        Membership.objects.create(user=cls.second_staff, dealership=cls.dealer, role='staff')
        cls.no_member = get_user_model().objects.create_user('audit-no-membership')
        foreign_customer = Customer.objects.create(dealership=cls.other, first_name='Foreign synthetic private')
        cls.foreign_book, _ = open_book(dealership_id=cls.other.pk, customer_id=foreign_customer.pk,
            actor=cls.users['foreign'], label='Private foreign account', source_reference='Synthetic',
            opening_on=date(2026, 1, 1), opening_amount='200', request_key=uuid4())
        cls.receipt, _ = record_receipt(dealership_id=cls.dealer.pk, book_id=cls.book.pk,
            actor=cls.users['staff'], amount='11', effective_on=date(2026, 2, 1),
            reason='Synthetic payment', request_key=uuid4())
        cls.foreign_receipt, _ = record_receipt(dealership_id=cls.other.pk, book_id=cls.foreign_book.pk,
            actor=cls.users['foreign'], amount='99', effective_on=date(2026, 2, 1),
            reason='Foreign synthetic reference', request_key=uuid4())

    def url(self, name, book=None, *extra):
        return reverse(name, args=[(book or self.book).pk, *extra])

    def test_owner_staff_viewer_read_and_export_only_own_account(self):
        reads = [self.url('bhph_account'), self.url('ledger_demo_detail'), self.url('account_export_review'),
                 self.url('bhph_account_receipt', None, self.receipt.pk)]
        for user in (self.owner, self.users['staff'], self.users['viewer']):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                for url in reads:
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200, url)
                    self.assertIn('no-store', response['Cache-Control'])
                    self.assertNotContains(response, 'Foreign synthetic reference')
                response = self.client.get(self.url('account_export_download'))
                self.assertEqual(response.status_code, 200)
                self.assertIn('no-store', response['Cache-Control'])
                with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
                    content = json.loads(bundle.read('account.json'))
                    self.assertEqual(content['account']['id'], self.book.pk)
                    self.assertNotIn(b'Foreign synthetic reference', bundle.read('journal.json'))
                self.assertTrue(DemoAccountExport.objects.filter(book=self.book, actor=user).exists())

    def test_cross_dealership_direct_urls_never_prepare_export(self):
        self.client.force_login(self.users['foreign'])
        urls = [self.url('bhph_account'), self.url('ledger_demo_detail'), self.url('account_export_review'),
                self.url('account_export_download'), self.url('bhph_account_receipt', None, self.receipt.pk),
                self.url('bhph_account_link'), self.url('ledger_demo_receipt')]
        with patch('finance.account_exports.build_bundle', side_effect=AssertionError('unauthorized bundle')):
            for url in urls:
                with self.subTest(url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 404)
                    self.assertIn('no-store', response['Cache-Control'])
            self.assertEqual(self.client.head(self.url('account_export_download')).status_code, 404)
        self.assertFalse(DemoAccountExport.objects.exists())

    def test_cross_account_receipt_ids_do_not_disclose(self):
        self.client.force_login(self.users['staff'])
        self.assertEqual(self.client.get(self.url('bhph_account_receipt', None, self.foreign_receipt.pk)).status_code, 404)
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(self.url('bhph_account_receipt', self.foreign_book, self.receipt.pk)).status_code, 404)

    def test_viewer_write_urls_are_denied_even_for_direct_requests(self):
        self.client.force_login(self.users['viewer'])
        for name in ('bhph_account_link', 'ledger_demo_receipt'):
            self.assertEqual(self.client.get(self.url(name)).status_code, 403)
            self.assertEqual(self.client.post(self.url(name), {}).status_code, 403)
        self.assertEqual(self.client.post(self.url('account_export_download')).status_code, 405)
        self.assertEqual(DemoPosting.objects.count(), 4)
        self.assertFalse(DemoAccountContext.objects.exists())
        self.assertFalse(DemoAccountExport.objects.exists())

    def test_token_cannot_be_replayed_by_other_staff_or_against_other_book(self):
        self.client.force_login(self.users['staff'])
        token = self.client.post(self.url('bhph_account_link'), {'deal': self.deal.pk}).context['token']
        second_book, _ = open_book(dealership_id=self.dealer.pk, customer_id=self.customer.pk,
            actor=self.users['staff'], label='Other synthetic', source_reference='Synthetic',
            opening_on=date(2026, 1, 1), opening_amount='10', request_key=uuid4())
        self.assertEqual(self.client.post(self.url('bhph_account_link', second_book), {'preview_token': token}).status_code, 403)
        self.client.force_login(self.second_staff)
        self.assertEqual(self.client.post(self.url('bhph_account_link'), {'preview_token': token}).status_code, 403)
        self.assertFalse(DemoAccountContext.objects.exists())

    def test_anonymous_and_missing_membership_cannot_access_or_export(self):
        for user, expected in ((None, 302), (self.no_member, 403)):
            if user: self.client.force_login(user)
            else: self.client.logout()
            for name in ('bhph_account', 'account_export_review', 'account_export_download'):
                self.assertEqual(self.client.get(self.url(name)).status_code, expected)
        self.assertFalse(DemoAccountExport.objects.exists())

    def test_gate_and_csrf_stop_direct_writes(self):
        self.client.force_login(self.users['staff'])
        with override_settings(DEMO_LEDGER_ENABLED=False):
            for name in ('bhph_account', 'bhph_account_link', 'account_export_review', 'account_export_download'):
                self.assertEqual(self.client.get(self.url(name)).status_code, 403)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.users['staff'])
        self.assertEqual(strict.post(self.url('bhph_account_link'), {'deal': self.deal.pk}).status_code, 403)
        self.assertFalse(DemoAccountContext.objects.exists())
        self.assertFalse(DemoAccountExport.objects.exists())

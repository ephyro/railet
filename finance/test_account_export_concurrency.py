# SPDX-License-Identifier: MPL-2.0
import io,json,zipfile
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from datetime import date
from uuid import uuid4
from unittest import skipUnless
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import connection,close_old_connections,OperationalError,transaction
from django.test import Client,TransactionTestCase,override_settings
from django.urls import reverse
from core.models import Membership
from . import account_exports,test_accounts as fixtures
from .services import record_receipt
from .models import DemoAccountExport, DemoBook


@skipUnless(connection.vendor=='postgresql','PostgreSQL row locks required')
@override_settings(DEMO_LEDGER_ENABLED=True)
class AccountExportConcurrencyTests(TransactionTestCase):
    def setUp(self):
        fixtures.AccountWorkspaceTests.setUpTestData.__func__(type(self))

    def test_export_rechecks_identity_after_book_and_membership_lock_waits(self):
        actor = self.users['staff']
        member = Membership.objects.get(user=actor)
        client = Client()
        client.force_login(actor)
        url = reverse('account_export_download', args=[self.book.pk])
        for lock_point in ('book', 'identity'):
            for revoked in ('inactive', 'foreign', 'removed', 'invalid_role'):
                for method in ('get', 'head'):
                    with self.subTest(lock_point=lock_point, revoked=revoked, method=method):
                        attempted = Event()
                        def download():
                            close_old_connections()
                            try:
                                def signal_lock(execute, sql, params, many, context):
                                    target = 'finance_demobook' if lock_point == 'book' else 'core_membership'
                                    if target in sql and 'FOR UPDATE' in sql:
                                        attempted.set()
                                    return execute(sql, params, many, context)
                                with connection.execute_wrapper(signal_lock):
                                    response = getattr(client, method)(url)
                                    return response.status_code, response.content, response.get('Cache-Control', '')
                            finally:
                                close_old_connections()

                        with patch('finance.account_exports.build_bundle', side_effect=AssertionError('Unauthorized ZIP preparation')), ThreadPoolExecutor(max_workers=1) as pool:
                            with transaction.atomic():
                                if lock_point == 'book':
                                    DemoBook.objects.select_for_update().get(pk=self.book.pk)
                                elif revoked == 'inactive':
                                    get_user_model().objects.select_for_update().get(pk=actor.pk)
                                else:
                                    Membership.objects.select_for_update().get(pk=member.pk)
                                future = pool.submit(download)
                                self.assertTrue(attempted.wait(timeout=20))
                                if revoked == 'inactive':
                                    get_user_model().objects.filter(pk=actor.pk).update(is_active=False)
                                elif revoked == 'foreign':
                                    Membership.objects.filter(pk=member.pk).update(dealership=self.other)
                                elif revoked == 'removed':
                                    Membership.objects.filter(pk=member.pk).delete()
                                else:
                                    Membership.objects.filter(pk=member.pk).update(role='invalid')
                            status, body, cache = future.result(timeout=20)
                        self.assertEqual(status, 403)
                        self.assertEqual(body, b'')
                        self.assertIn('no-store', cache)
                        self.assertEqual(DemoAccountExport.objects.count(), 0)
                        get_user_model().objects.filter(pk=actor.pk).update(is_active=True)
                        member, _ = Membership.objects.update_or_create(user=actor, defaults={'dealership': self.dealer, 'role': 'staff'})

    def test_receipt_cannot_interleave_with_export_capture(self):
        locked=Event();release=Event();original=account_exports.build_bundle
        def paused(*args,**kwargs):
            locked.set()
            if not release.wait(10):raise RuntimeError('Export synchronization timed out')
            return original(*args,**kwargs)
        def download():
            close_old_connections()
            try:
                client=Client();client.force_login(get_user_model().objects.get(pk=self.users['staff'].pk))
                return client.get(reverse('account_export_download',args=[self.book.pk]))
            finally:close_old_connections()
        def try_receipt():
            close_old_connections()
            try:
                with connection.cursor() as cursor:cursor.execute("SET lock_timeout='200ms'")
                actor=get_user_model().objects.get(pk=self.users['staff'].pk)
                try:
                    record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=actor,
                        amount='25',effective_on=date(2026,2,1),reason='Synthetic concurrency receipt',request_key=uuid4())
                except OperationalError as error:
                    return 'lock timeout' in str(error)
                return False
            finally:close_old_connections()
        with patch('finance.account_exports.build_bundle',side_effect=paused),ThreadPoolExecutor(max_workers=2) as pool:
            exported=pool.submit(download)
            try:
                self.assertTrue(locked.wait(10))
                self.assertTrue(pool.submit(try_receipt).result(timeout=10))
            finally:release.set()
            response=exported.result(timeout=10)
        self.assertEqual(response.status_code,200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(len(json.loads(archive.read('journal.json'))),1)
            self.assertEqual(json.loads(archive.read('account.json'))['reconciliation']['net_debit']['unapplied'],0)
        record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.users['staff'],
            amount='25',effective_on=date(2026,2,1),reason='Synthetic receipt after export',request_key=uuid4())
        self.assertEqual(self.book.postings.count(),2)
        self.assertEqual(DemoAccountExport.objects.get().posting_count,1)

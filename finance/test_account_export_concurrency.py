# SPDX-License-Identifier: MPL-2.0
import io,json,zipfile
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from datetime import date
from uuid import uuid4
from unittest import skipUnless
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import connection,close_old_connections,OperationalError
from django.test import Client,TransactionTestCase,override_settings
from django.urls import reverse
from . import account_exports,test_accounts as fixtures
from .services import record_receipt
from .models import DemoAccountExport


@skipUnless(connection.vendor=='postgresql','PostgreSQL row locks required')
@override_settings(DEMO_LEDGER_ENABLED=True)
class AccountExportConcurrencyTests(TransactionTestCase):
    def setUp(self):
        fixtures.AccountWorkspaceTests.setUpTestData.__func__(type(self))

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

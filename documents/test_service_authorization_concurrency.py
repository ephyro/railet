# SPDX-License-Identifier: MPL-2.0
"""PostgreSQL regression tests for private-document service authorization."""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings

from core.models import Dealership, Membership
from customers.models import Customer
from deals.models import DraftDeal
from inventory.models import Vehicle
from . import tests as scenarios
from . import services, invoice_views, acquisition_views
from .acquisition_views import upload_acquisition_file, change_acquisition_file_state
from .invoice_views import upload_invoice
from .models import DealFile, DealFileEvent, VehicleAcquisitionFile, VehicleAcquisitionFileEvent, VehicleInvoice
from .services import upload_deal_file, change_deal_file_state


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL row locks required')
@override_settings(DEAL_FILES_DEMO_ENABLED=True, RECON_DEMO_ENABLED=True)
class DocumentAuthorizationRaceTests(scenarios.TemporaryDealFileStorageMixin, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.dealer = Dealership.objects.create(name='Synthetic document race')
        self.actor = get_user_model().objects.create_user(username='synthetic-document-race')
        Membership.objects.create(user=self.actor, dealership=self.dealer, role='staff')
        self.vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='RACE', year=2022, make='Demo', model='Car')
        buyer = Customer.objects.create(dealership=self.dealer, first_name='Synthetic')
        self.deal = DraftDeal.objects.create(dealership=self.dealer, vehicle=self.vehicle, buyer=buyer)
        self.saved, _ = upload_deal_file(deal_id=self.deal.pk, dealership_id=self.dealer.pk, actor=self.actor,
            title='Synthetic existing', upload_key=uuid.uuid4(), pdf_bytes=scenarios.PDF_BYTES)
        self.saved_acquisition, _ = upload_acquisition_file(vehicle_id=self.vehicle.pk, dealership_id=self.dealer.pk,
            actor=self.actor, title='Synthetic existing acquisition', upload_key=uuid.uuid4(), pdf_bytes=scenarios.PDF_BYTES)

    def test_role_or_active_revocation_before_parent_lock_denies_all_mutations(self):
        def upload_deal(actor):
            return upload_deal_file(deal_id=self.deal.pk, dealership_id=self.dealer.pk, actor=actor,
                title='Synthetic new', upload_key=uuid.uuid4(), pdf_bytes=scenarios.PDF_BYTES)
        def archive_deal(actor):
            return change_deal_file_state(deal_id=self.deal.pk, dealership_id=self.dealer.pk,
                file_id=self.saved.pk, actor=actor, action='archive', reason='Synthetic test')
        def invoice(actor):
            return upload_invoice(vehicle_id=self.vehicle.pk, dealership_id=self.dealer.pk, actor=actor,
                title='Synthetic invoice', upload_key=uuid.uuid4(), pdf_bytes=scenarios.PDF_BYTES, cost_id=None)
        def acquisition(actor):
            return upload_acquisition_file(vehicle_id=self.vehicle.pk, dealership_id=self.dealer.pk, actor=actor,
                title='Synthetic acquisition', upload_key=uuid.uuid4(), pdf_bytes=scenarios.PDF_BYTES)
        def archive_acquisition(actor):
            return change_acquisition_file_state(vehicle_id=self.vehicle.pk, dealership_id=self.dealer.pk,
                file_id=self.saved_acquisition.pk, actor=actor, action='archive', reason='Synthetic test')

        for operation in (upload_deal, archive_deal, invoice, acquisition, archive_acquisition):
            for change in ('role', 'active'):
                with self.subTest(operation=operation.__name__, change=change):
                    Membership.objects.filter(user=self.actor).update(role='staff')
                    get_user_model().objects.filter(pk=self.actor.pk).update(is_active=True)
                    started = Event()
                    backend = []
                    def run():
                        close_old_connections()
                        try:
                            actor = get_user_model().objects.get(pk=self.actor.pk)
                            with connection.cursor() as cursor:
                                cursor.execute('SELECT pg_backend_pid()')
                                backend.append(cursor.fetchone()[0])
                            started.set()
                            try:
                                operation(actor)
                            except PermissionDenied:
                                return 'denied'
                            return 'unexpected success'
                        finally:
                            close_old_connections()
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        with transaction.atomic():
                            Dealership.objects.select_for_update().get(pk=self.dealer.pk)
                            future = pool.submit(run)
                            self.assertTrue(started.wait(5))
                            deadline = time.monotonic() + 5
                            while time.monotonic() < deadline:
                                with connection.cursor() as cursor:
                                    cursor.execute('SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s', [backend[0]])
                                    row = cursor.fetchone()
                                if row and row[0] == 'Lock':
                                    break
                                time.sleep(.02)
                            else:
                                self.fail('Document operation did not wait on the dealership lock')
                            if change == 'role':
                                Membership.objects.filter(user=self.actor).update(role='viewer')
                            else:
                                get_user_model().objects.filter(pk=self.actor.pk).update(is_active=False)
                        self.assertEqual(future.result(timeout=10), 'denied')
                    self.saved.refresh_from_db()
                    self.assertIsNone(self.saved.archived_at)
                    self.assertEqual(DealFile.objects.count(), 1)
                    self.assertEqual(DealFileEvent.objects.count(), 1)
                    self.assertFalse(VehicleInvoice.objects.exists())
                    self.saved_acquisition.refresh_from_db()
                    self.assertIsNone(self.saved_acquisition.archived_at)
                    self.assertEqual(VehicleAcquisitionFile.objects.count(), 1)
                    self.assertEqual(VehicleAcquisitionFileEvent.objects.count(), 1)

    def test_authorization_rows_stay_locked_through_upload_commit(self):
        operations = (
            (services, lambda actor: upload_deal_file(deal_id=self.deal.pk, dealership_id=self.dealer.pk,
                actor=actor, title='Synthetic new', upload_key=uuid.uuid4(), pdf_bytes=scenarios.PDF_BYTES)),
            (invoice_views, lambda actor: upload_invoice(vehicle_id=self.vehicle.pk, dealership_id=self.dealer.pk,
                actor=actor, title='Synthetic invoice', upload_key=uuid.uuid4(), pdf_bytes=scenarios.PDF_BYTES, cost_id=None)),
            (acquisition_views, lambda actor: upload_acquisition_file(vehicle_id=self.vehicle.pk,
                dealership_id=self.dealer.pk, actor=actor, title='Synthetic acquisition',
                upload_key=uuid.uuid4(), pdf_bytes=scenarios.PDF_BYTES)),
        )
        for module, operation in operations:
            for change in ('role', 'active'):
                with self.subTest(module=module.__name__, change=change):
                    Membership.objects.filter(user=self.actor).update(role='staff')
                    get_user_model().objects.filter(pk=self.actor.pk).update(is_active=True)
                    checked, release, updater_started = Event(), Event(), Event()
                    backend = []
                    real_check = module._require_locked_editor
                    def pause_after_check(actor, dealership_id):
                        real_check(actor, dealership_id)
                        checked.set()
                        if not release.wait(10):
                            raise AssertionError('Timed out waiting to release the upload')
                    def upload():
                        close_old_connections()
                        try:
                            return operation(get_user_model().objects.get(pk=self.actor.pk))
                        finally:
                            close_old_connections()
                    def revoke():
                        close_old_connections()
                        try:
                            with connection.cursor() as cursor:
                                cursor.execute('SELECT pg_backend_pid()')
                                backend.append(cursor.fetchone()[0])
                            updater_started.set()
                            if change == 'role':
                                Membership.objects.filter(user=self.actor).update(role='viewer')
                            else:
                                get_user_model().objects.filter(pk=self.actor.pk).update(is_active=False)
                        finally:
                            close_old_connections()
                    with patch.object(module, '_require_locked_editor', side_effect=pause_after_check):
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            posting = pool.submit(upload)
                            try:
                                self.assertTrue(checked.wait(5))
                                revocation = pool.submit(revoke)
                                self.assertTrue(updater_started.wait(5))
                                deadline = time.monotonic() + 5
                                while time.monotonic() < deadline:
                                    with connection.cursor() as cursor:
                                        cursor.execute('SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s', [backend[0]])
                                        row = cursor.fetchone()
                                    if row and row[0] == 'Lock':
                                        break
                                    time.sleep(.02)
                                else:
                                    self.fail('Revocation did not wait on the locked authorization row')
                            finally:
                                release.set()
                            self.assertIsNotNone(posting.result(timeout=10))
                            revocation.result(timeout=10)

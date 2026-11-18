# SPDX-License-Identifier: MPL-2.0
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import Mock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Dealership, Membership
from customers.models import Customer
from deals.models import DraftDeal
from inventory.models import Vehicle, VehiclePhoto
from .models import DealFile, DealFileEvent, VehicleAcquisitionFile, VehicleAcquisitionFileEvent, VehicleInvoice, VehicleInvoiceEvent


class PrivateDownloadFixture:
    def setUp(self):
        super().setUp()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        override = override_settings(MEDIA_ROOT=temporary.name, DEAL_FILES_DEMO_ENABLED=True, RECON_DEMO_ENABLED=True)
        override.enable()
        self.addCleanup(override.disable)
        self.dealer = Dealership.objects.create(name='Synthetic download dealer')
        self.other = Dealership.objects.create(name='Synthetic foreign download dealer')
        self.actor = get_user_model().objects.create_user('synthetic-download-actor')
        self.member = Membership.objects.create(user=self.actor, dealership=self.dealer, role='owner')
        vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='DOWNLOAD-1', year=2020, make='Synthetic', model='Car')
        buyer = Customer.objects.create(dealership=self.dealer, first_name='Synthetic', last_name='Buyer')
        deal = DraftDeal.objects.create(dealership=self.dealer, vehicle=vehicle, buyer=buyer)
        pdf = b'%PDF-1.7\nSynthetic private bytes\n%%EOF\n'
        blob_names = ['deal-files/synthetic.pdf', 'vehicle-invoices/synthetic.pdf', 'vehicle-acquisition/synthetic.pdf']
        for name in blob_names:
            path = Path(temporary.name) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(pdf)
        for name in ('vehicles/synthetic.jpg', 'vehicles/synthetic-thumb.jpg'):
            path = Path(temporary.name) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic image')
        common = dict(title='Synthetic PDF', sha256=hashlib.sha256(pdf).hexdigest(), byte_size=len(pdf), created_by=self.actor)
        self.deal_file = DealFile.objects.create(deal=deal, blob=blob_names[0], upload_key=uuid4(), **common)
        self.invoice = VehicleInvoice.objects.create(vehicle=vehicle, blob=blob_names[1], upload_key=uuid4(), **common)
        self.acquisition = VehicleAcquisitionFile.objects.create(vehicle=vehicle, blob=blob_names[2], upload_key=uuid4(), **common)
        self.photo = VehiclePhoto.objects.create(vehicle=vehicle, created_by=self.actor, image='vehicles/synthetic.jpg', thumbnail='vehicles/synthetic-thumb.jpg', is_primary=True)
        self.urls = [reverse('deal_file_download', args=[deal.pk, self.deal_file.pk]),
                     reverse('vehicle_invoice_download', args=[vehicle.pk, self.invoice.pk]),
                     reverse('vehicle_acquisition_file_download', args=[vehicle.pk, self.acquisition.pk]),
                     reverse('vehicle_photo_file', args=[self.photo.pk]), reverse('vehicle_photo_thumbnail', args=[self.photo.pk])]
        self.client.force_login(self.actor)

    def assert_no_download_events(self):
        self.assertEqual((DealFileEvent.objects.count(), VehicleInvoiceEvent.objects.count(), VehicleAcquisitionFileEvent.objects.count()), (0, 0, 0))


class PrivateDownloadAuthorizationTests(PrivateDownloadFixture, TestCase):
    def test_response_is_closed_if_outer_commit_fails(self):
        from core.access import authorized_private_read
        response = Mock()
        request = SimpleNamespace(member=self.member, user=self.actor)
        with patch('core.access.transaction.atomic') as atomic, \
             patch('core.access.Dealership.objects.select_for_update') as dealer_lock, \
             patch('core.access.Membership.objects.select_for_update') as member_lock:
            atomic.return_value.__exit__.side_effect = RuntimeError('synthetic commit failure')
            dealer_lock.return_value.filter.return_value.exists.return_value = True
            member_lock.return_value.select_related.return_value.filter.return_value.first.return_value = self.member
            with self.assertRaisesRegex(RuntimeError, 'synthetic commit failure'):
                authorized_private_read(lambda request: response)(request)
        response.close.assert_called_once_with()

    def test_revocation_before_locked_check_denies_get_and_head(self):
        select = Membership.objects.select_for_update
        for revoked in ('inactive', 'foreign', 'removed', 'invalid_role'):
            for url in self.urls:
                for method in ('get', 'head'):
                    with self.subTest(revoked=revoked, url=url, method=method):
                        def revoke():
                            if revoked == 'inactive':
                                get_user_model().objects.filter(pk=self.actor.pk).update(is_active=False)
                            elif revoked == 'foreign':
                                Membership.objects.filter(pk=self.member.pk).update(dealership=self.other)
                            elif revoked == 'removed':
                                Membership.objects.filter(pk=self.member.pk).delete()
                            else:
                                Membership.objects.filter(pk=self.member.pk).update(role='invalid')
                            return select()
                        with patch('core.access.Membership.objects.select_for_update', side_effect=revoke):
                            response = getattr(self.client, method)(url)
                        self.assertEqual(response.status_code, 403)
                        self.assertIn('no-store', response['Cache-Control'])
                        self.assert_no_download_events()

    def test_role_downgrade_hides_archived_bytes(self):
        DealFile.objects.filter(pk=self.deal_file.pk).update(archived_at=timezone.now())
        VehicleAcquisitionFile.objects.filter(pk=self.acquisition.pk).update(archived_at=timezone.now())
        VehiclePhoto.objects.filter(pk=self.photo.pk).update(archived_at=timezone.now(), is_primary=False)
        select = Membership.objects.select_for_update
        def downgrade():
            Membership.objects.filter(pk=self.member.pk).update(role='viewer')
            return select()
        for url in (self.urls[0], self.urls[2], self.urls[3], self.urls[4]):
            with self.subTest(url=url), patch('core.access.Membership.objects.select_for_update', side_effect=downgrade):
                self.assertEqual(self.client.get(url).status_code, 404)
        self.assert_no_download_events()


@skipUnless(connection.vendor == 'postgresql', 'Row locking requires PostgreSQL')
class PrivateDownloadRaceTests(PrivateDownloadFixture, TransactionTestCase):
    def test_membership_revocation_and_archive_downgrade_after_lock_wait(self):
        for archived in (False, True):
            if archived:
                DealFile.objects.filter(pk=self.deal_file.pk).update(archived_at=timezone.now())
                VehicleAcquisitionFile.objects.filter(pk=self.acquisition.pk).update(archived_at=timezone.now())
                VehiclePhoto.objects.filter(pk=self.photo.pk).update(archived_at=timezone.now(), is_primary=False)
            scenarios = [('viewer', url) for url in (self.urls[0], self.urls[2], self.urls[3], self.urls[4])] if archived else [
                (change, url) for change in ('inactive', 'foreign', 'removed', 'invalid_role') for url in self.urls]
            for revoked, url in scenarios:
                for method in ('get', 'head'):
                    with self.subTest(archived=archived, revoked=revoked, url=url, method=method):
                        attempted = Event()

                        def download():
                            close_old_connections()
                            try:
                                def signal_lock(execute, sql, params, many, context):
                                    if 'core_membership' in sql and 'FOR UPDATE' in sql:
                                        attempted.set()
                                    return execute(sql, params, many, context)
                                with connection.execute_wrapper(signal_lock):
                                    response = getattr(self.client, method)(url)
                                    return response.status_code, response.get('Cache-Control', '')
                            finally:
                                close_old_connections()

                        with ThreadPoolExecutor(max_workers=1) as pool:
                            with transaction.atomic():
                                if revoked == 'inactive':
                                    get_user_model().objects.select_for_update().get(pk=self.actor.pk)
                                else:
                                    Membership.objects.select_for_update().get(pk=self.member.pk)
                                future = pool.submit(download)
                                self.assertTrue(attempted.wait(timeout=20))
                                if revoked == 'inactive':
                                    get_user_model().objects.filter(pk=self.actor.pk).update(is_active=False)
                                elif revoked == 'foreign':
                                    Membership.objects.filter(pk=self.member.pk).update(dealership=self.other)
                                elif revoked == 'removed':
                                    Membership.objects.filter(pk=self.member.pk).delete()
                                else:
                                    Membership.objects.filter(pk=self.member.pk).update(role=revoked if revoked == 'viewer' else 'invalid')
                            status, cache = future.result(timeout=20)
                        self.assertEqual(status, 404 if revoked == 'viewer' else 403)
                        self.assertIn('no-store', cache)
                        self.assert_no_download_events()
                        get_user_model().objects.filter(pk=self.actor.pk).update(is_active=True)
                        self.member, _ = Membership.objects.update_or_create(user=self.actor, defaults={'dealership': self.dealer, 'role': 'owner'})

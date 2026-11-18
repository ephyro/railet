# SPDX-License-Identifier: MPL-2.0
import hashlib
import io
import json
import tempfile
import uuid
import zipfile
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from core.dealership_export import build_package
from core.models import Dealership, Membership
from inventory.models import Vehicle
from .acquisition_views import change_acquisition_file_state, upload_acquisition_file
from .models import VehicleAcquisitionFile, VehicleAcquisitionFileEvent
from .services import MAX_FILE_BYTES, UploadKeyConflict

PDF = b'%PDF-1.7\nSynthetic vehicle acquisition evidence\n%%EOF\n'


@override_settings(
    DEBUG=True,
    DEAL_FILES_DEMO_ENABLED=True,
    CUSTOMER_ACTIVITY_DEMO_ENABLED=True,
    RECON_DEMO_ENABLED=True,
    DEMO_COMPLETION_ENABLED=True,
    DEMO_PACKETS_ENABLED=True,
    DEMO_LEDGER_ENABLED=True,
    DEMO_SERVICING_ENABLED=True,
)
class VehicleAcquisitionFileTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.temp.name)
        self.override.enable()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.override.disable)

        self.dealer = Dealership.objects.create(name='Synthetic acquisition dealer')
        self.other = Dealership.objects.create(name='Foreign acquisition dealer')
        self.users = {}
        for label, role, dealer in [
            ('owner', 'owner', self.dealer),
            ('staff', 'staff', self.dealer),
            ('viewer', 'viewer', self.dealer),
            ('foreign', 'owner', self.other),
        ]:
            user = get_user_model().objects.create_user('acq-' + label)
            Membership.objects.create(user=user, dealership=dealer, role=role)
            self.users[label] = user

        self.vehicle = Vehicle.objects.create(
            dealership=self.dealer, stock_number='ACQ-1', year=2021, make='Synthetic', model='Sedan',
            status='acquired', title_brand='unknown', title_received=False,
        )
        self.foreign_vehicle = Vehicle.objects.create(
            dealership=self.other, stock_number='FOREIGN-ACQ', year=2021, make='Foreign', model='Sedan',
        )
        self.client.force_login(self.users['staff'])
        self.url = reverse('vehicle_acquisition_files', args=[self.vehicle.pk])

    def upload(self, *, title='Synthetic auction bill of sale', description='Practice intake PDF', data=PDF, key=None):
        return self.client.post(
            self.url,
            {
                'title': title,
                'description': description,
                'upload_key': key or uuid.uuid4(),
                'pdf_file': SimpleUploadedFile('acquisition.pdf', data, content_type='application/pdf'),
            },
        )

    def test_upload_download_archive_restore_and_no_ownership_or_date_side_effects(self):
        # Vehicle detail links to acquisition attachments
        detail_res = self.client.get(reverse('vehicle_detail', args=[self.vehicle.pk]))
        self.assertContains(detail_res, self.url)

        key = uuid.uuid4()
        self.assertEqual(self.upload(key=key).status_code, 302)
        # Idempotent retry with same upload_key
        self.assertEqual(self.upload(key=key).status_code, 302)
        self.assertEqual(VehicleAcquisitionFile.objects.count(), 1)
        record = VehicleAcquisitionFile.objects.get()
        self.assertEqual(record.description, 'Practice intake PDF')

        # Uploading does not set acquired_on, sold_on, title_received, or change vehicle status
        self.vehicle.refresh_from_db()
        self.assertIsNone(self.vehicle.acquired_on)
        self.assertIsNone(self.vehicle.sold_on)
        self.assertFalse(self.vehicle.title_received)
        self.assertEqual(self.vehicle.status, 'acquired')

        # Page explicitly labels attachment as staff-provided and unverified
        page = self.client.get(self.url)
        self.assertContains(page, 'Staff-provided, unverified')
        self.assertContains(page, 'Practice intake PDF')
        self.assertIn('no-store', page['Cache-Control'])

        # Download returns exact PDF bytes with nosniff/sandbox headers and records event only on GET (not HEAD)
        dl_url = reverse('vehicle_acquisition_file_download', args=[self.vehicle.pk, record.pk])
        dl_res = self.client.get(dl_url)
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(dl_res.content, PDF)
        self.assertIn('attachment', dl_res['Content-Disposition'])
        self.assertEqual(dl_res['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(dl_res['Content-Security-Policy'], 'sandbox')
        head_res = self.client.head(dl_url)
        self.assertEqual(head_res.status_code, 200)
        self.assertEqual(head_res.content, b'')
        self.assertEqual(
            list(record.events.order_by('pk').values_list('action', flat=True)),
            ['upload', 'download'],
        )

        # Archive requires reason; hides from viewer; staff can still download and restore
        act_url = reverse('vehicle_acquisition_file_action', args=[self.vehicle.pk, record.pk])
        prefix = f'file-{record.pk}-archive'
        bad_arch = self.client.post(act_url, {f'{prefix}-action': 'archive', f'{prefix}-reason': ''})
        self.assertContains(bad_arch, 'Enter a reason to archive this file.')

        ok_arch = self.client.post(act_url, {f'{prefix}-action': 'archive', f'{prefix}-reason': 'Replaced by clearer synthetic scan'})
        self.assertEqual(ok_arch.status_code, 302)
        record.refresh_from_db()
        self.assertIsNotNone(record.archived_at)

        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.client.get(dl_url).status_code, 404)
        self.assertNotContains(self.client.get(self.url), 'Synthetic auction bill of sale')

        self.client.force_login(self.users['staff'])
        self.assertEqual(self.client.get(dl_url).status_code, 200)
        restore_prefix = f'file-{record.pk}-restore'
        self.assertEqual(self.client.post(act_url, {f'{restore_prefix}-action': 'restore'}).status_code, 302)
        record.refresh_from_db()
        self.assertIsNone(record.archived_at)

    def test_cross_dealer_viewer_permissions_csrf_and_gates(self):
        self.upload()
        record = VehicleAcquisitionFile.objects.get()
        dl_url = reverse('vehicle_acquisition_file_download', args=[self.vehicle.pk, record.pk])
        act_url = reverse('vehicle_acquisition_file_action', args=[self.vehicle.pk, record.pk])

        # Viewer can view/download active files, but cannot upload or archive
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.get(dl_url).status_code, 200)
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(self.client.post(act_url, {}).status_code, 403)
        with self.assertRaises(PermissionDenied):
            upload_acquisition_file(
                vehicle_id=self.vehicle.pk, dealership_id=self.dealer.pk, actor=self.users['viewer'],
                title='Denied', upload_key=uuid.uuid4(), pdf_bytes=PDF,
            )

        # Foreign dealership gets 404 on list, upload, action, and download
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.upload().status_code, 404)
        self.assertEqual(self.client.get(dl_url).status_code, 404)
        self.assertEqual(self.client.post(act_url, {}).status_code, 404)

        # CSRF and disabled gate (both HTTP views and direct service calls)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.users['staff'])
        self.assertEqual(strict.post(self.url, {}).status_code, 403)
        with override_settings(DEAL_FILES_DEMO_ENABLED=False):
            self.client.force_login(self.users['staff'])
            self.assertEqual(self.client.get(self.url).status_code, 404)
            self.assertEqual(self.client.get(dl_url).status_code, 404)
            with self.assertRaises(PermissionDenied):
                upload_acquisition_file(
                    vehicle_id=self.vehicle.pk, dealership_id=self.dealer.pk, actor=self.users['staff'],
                    title='Gated', upload_key=uuid.uuid4(), pdf_bytes=PDF,
                )
            with self.assertRaises(PermissionDenied):
                change_acquisition_file_state(
                    vehicle_id=self.vehicle.pk, dealership_id=self.dealer.pk, file_id=record.pk,
                    actor=self.users['staff'], action='archive', reason='Gated',
                )

    def test_download_roles_cache_and_shared_storage_alias(self):
        self.upload()
        record = VehicleAcquisitionFile.objects.get()
        url = reverse('vehicle_acquisition_file_download', args=[self.vehicle.pk, record.pk])
        for name, expected in [('owner', 200), ('staff', 200), ('viewer', 200), ('foreign', 404)]:
            self.client.force_login(self.users[name])
            for method in (self.client.get, self.client.head):
                response = method(url)
                self.assertEqual(response.status_code, expected)
                self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.client.logout()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        VehicleAcquisitionFile.objects.create(vehicle=self.foreign_vehicle, title='Foreign', blob=record.blob.name.replace('vehicle-acquisition/', 'vehicle-acquisition/./'), sha256=record.sha256, byte_size=record.byte_size, created_by=self.users['foreign'])
        self.client.force_login(self.users['staff'])
        before = record.events.filter(action='download').count()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(record.events.filter(action='download').count(), before)

    def test_failed_download_audit_returns_no_file(self):
        self.upload()
        record = VehicleAcquisitionFile.objects.get()
        url = reverse('vehicle_acquisition_file_download', args=[self.vehicle.pk, record.pk])
        with patch('documents.acquisition_views.VehicleAcquisitionFileEvent.objects.create', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.client.get(url)
        self.assertFalse(record.events.filter(action='download').exists())

    def test_validation_tampering_missing_blob_and_db_immutability_guards(self):
        # Invalid PDFs and conflicting key reuse rejected
        for bad_bytes in (b'', b'not-a-pdf', b'%PDF-1.7\nno-eof', b'%PDF-' + b'x' * MAX_FILE_BYTES + b'%%EOF'):
            self.assertEqual(self.upload(data=bad_bytes).status_code, 200)
        self.assertFalse(VehicleAcquisitionFile.objects.exists())

        key = uuid.uuid4()
        self.assertEqual(self.upload(key=key).status_code, 302)
        conflict = self.upload(key=key, description='Different description')
        self.assertEqual(conflict.status_code, 200)
        self.assertContains(conflict, 'Start a fresh upload')
        # Cross-actor retry with identical file facts is also rejected
        self.client.force_login(self.users['owner'])
        actor_conflict = self.upload(key=key)
        self.assertEqual(actor_conflict.status_code, 200)
        self.assertContains(actor_conflict, 'Start a fresh upload')
        with self.assertRaises(UploadKeyConflict):
            upload_acquisition_file(
                vehicle_id=self.vehicle.pk, dealership_id=self.dealer.pk, actor=self.users['owner'],
                title='Synthetic auction bill of sale', description='Practice intake PDF',
                upload_key=key, pdf_bytes=PDF,
            )
        self.client.force_login(self.users['staff'])
        self.assertEqual(VehicleAcquisitionFile.objects.count(), 1)

        record = VehicleAcquisitionFile.objects.get()
        event = VehicleAcquisitionFileEvent.objects.get()

        # Database triggers block deleting files, mutating immutable file columns, or mutating/deleting events
        for mutation in (
            lambda: VehicleAcquisitionFile.objects.filter(pk=record.pk).update(title='Tampered'),
            lambda: VehicleAcquisitionFile.objects.filter(pk=record.pk).update(sha256='0' * 64),
            lambda: VehicleAcquisitionFile.objects.filter(pk=record.pk).delete(),
            lambda: VehicleAcquisitionFileEvent.objects.filter(pk=event.pk).update(action='download'),
            lambda: VehicleAcquisitionFileEvent.objects.filter(pk=event.pk).delete(),
        ):
            with self.assertRaises(DatabaseError), transaction.atomic():
                mutation()

        # Tampered file on disk fails closed with 409; missing file returns 404
        dl_url = reverse('vehicle_acquisition_file_download', args=[self.vehicle.pk, record.pk])
        with record.blob.open('wb') as f:
            f.write(b'%PDF-1.7\ntampered\n%%EOF\n')
        self.assertEqual(self.client.get(dl_url).status_code, 409)
        record.blob.delete(save=False)
        self.assertEqual(self.client.get(dl_url).status_code, 404)

    def test_dealership_export_includes_retained_and_archived_acquisition_files(self):
        self.upload(title='Synthetic auction receipt', description='Archived test receipt')
        record = VehicleAcquisitionFile.objects.get()
        act_url = reverse('vehicle_acquisition_file_action', args=[self.vehicle.pk, record.pk])
        prefix = f'file-{record.pk}-archive'
        self.client.post(act_url, {f'{prefix}-action': 'archive', f'{prefix}-reason': 'Keep in archive for export'})

        with transaction.atomic():
            bundle = build_package(dealership_id=self.dealer.pk, actor=self.users['owner'])
        with zipfile.ZipFile(io.BytesIO(bundle)) as outer:
            with zipfile.ZipFile(io.BytesIO(outer.read('documents.zip'))) as docs_zip:
                artifact_path = f'vehicle-acquisition/{record.pk}.pdf'
                self.assertEqual(docs_zip.read(artifact_path), PDF)
                meta = json.loads(docs_zip.read('metadata.json'))
                self.assertEqual(len(meta['vehicle_acquisition_files']), 1)
                self.assertEqual(meta['vehicle_acquisition_files'][0]['id'], record.pk)
                self.assertEqual(meta['vehicle_acquisition_files'][0]['description'], 'Archived test receipt')
                self.assertIsNotNone(meta['vehicle_acquisition_files'][0]['archived_at'])
                self.assertEqual(
                    [e['action'] for e in meta['vehicle_acquisition_file_events']],
                    ['upload', 'archive'],
                )

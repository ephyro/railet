# SPDX-License-Identifier: MPL-2.0
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.utils import timezone
from core.models import AuditEvent, Dealership, Membership
from core.test_audit_guards import legacy_mismatch_fixture
from .export import (
    FORMAT_VERSION,
    InventoryExportError,
    InventoryExportTooLarge,
    InventoryPhotoArtifactError,
    export_inventory,
)
from .models import (
    ReconTask,
    Vehicle,
    VehiclePhoto,
)
from .photos import add_photos, change_photo, normalize_photo
from .reconditioning import add_cost, add_task, edit_task, reverse_cost, save_vendor
from .test_photos import photo_file


@override_settings(DEBUG=True, RECON_DEMO_ENABLED=True)
class InventoryExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealership.objects.create(name='Synthetic inventory export dealer')
        cls.other = Dealership.objects.create(name='Foreign inventory export dealer')
        cls.users = {}
        for label, role, dealer in [
            ('owner', 'owner', cls.dealer),
            ('staff', 'staff', cls.dealer),
            ('viewer', 'viewer', cls.dealer),
            ('foreign', 'owner', cls.other),
        ]:
            user = get_user_model().objects.create_user('inv-export-' + label)
            Membership.objects.create(user=user, dealership=dealer, role=role)
            cls.users[label] = user

        cls.vehicle = Vehicle.objects.create(
            dealership=cls.dealer, stock_number='EXP-1', vin='1SYNTHETICEXPORT01',
            year=2021, make='Synthetic', model='Export Sedan',
            title_brand='rebuilt', title_received=True,
            odometer_reading=45000, odometer_unit='miles', odometer_status='actual',
            status='sold', acquired_on=date(2026, 9, 1), sold_on=date(2026, 10, 15),
            acquisition_cost=Decimal('5000.10'), recon_cost=Decimal('100.20'),
            asking_price=Decimal('6995.00'), notes='=synthetic note', revision=2,
        )
        cls.unpriced_vehicle = Vehicle.objects.create(
            dealership=cls.dealer, stock_number='EXP-2', year=2020, make='Synthetic', model='Basic',
        )
        cls.foreign_vehicle = Vehicle.objects.create(
            dealership=cls.other, stock_number='FOREIGN-SECRET-STOCK', vin='FOREIGN-SECRET-VIN',
            year=2022, make='Foreign', model='Secret', notes='FOREIGN-PRIVATE-NOTE',
        )

        cls.vendor = save_vendor(
            dealership=cls.dealer, actor=cls.users['staff'],
            data={
                'name': 'Synthetic Tire Shop', 'contact_name': 'Alex Tire',
                'phone': '555-0122', 'email': 'tire@example.invalid',
                'address': '10 Synthetic Way', 'notes': 'Internal vendor note',
            },
        )
        save_vendor(
            dealership=cls.dealer, actor=cls.users['owner'], vendor_id=cls.vendor.pk,
            data={
                'revision': 1, 'name': 'Synthetic Tire & Wheel', 'contact_name': 'Alex Tire',
                'phone': '555-0199', 'email': 'tire@example.invalid',
                'address': '10 Synthetic Way', 'notes': 'Updated vendor note',
            },
        )
        foreign_vendor = save_vendor(
            dealership=cls.other, actor=cls.users['foreign'],
            data={'name': 'FOREIGN-PRIVATE-VENDOR'},
        )

        cls.task = add_task(
            vehicle_id=cls.vehicle.pk, dealership=cls.dealer, actor=cls.users['staff'],
            data={
                'request_key': uuid4(), 'title': 'Mount tires', 'detail': 'Front pair',
                'vendor': cls.vendor, 'new_vendor': '', 'assigned_to': cls.users['staff'],
                'due_on': date(2026, 10, 1),
            },
        )
        edit_task(
            vehicle_id=cls.vehicle.pk, dealership=cls.dealer, actor=cls.users['owner'],
            task_id=cls.task.pk,
            data={
                'revision': 1, 'title': 'Mount and balance tires', 'detail': 'All four wheels',
                'status': 'done', 'vendor': cls.vendor, 'new_vendor': '',
                'assigned_to': cls.users['owner'], 'due_on': date(2026, 10, 2),
            },
        )
        ReconTask.objects.create(
            vehicle=cls.foreign_vehicle, title='FOREIGN-PRIVATE-TASK',
            vendor=foreign_vendor, created_by=cls.users['foreign'],
        )

        cls.cost = add_cost(
            vehicle_id=cls.vehicle.pk, dealership=cls.dealer, actor=cls.users['staff'],
            data={
                'request_key': uuid4(), 'category': 'parts', 'description': 'Synthetic tire set',
                'amount': Decimal('420.50'), 'effective_on': date(2026, 10, 2),
                'vendor': cls.vendor, 'new_vendor': '', 'task': cls.task,
            },
        )
        cls.reversal = reverse_cost(
            vehicle_id=cls.vehicle.pk, dealership=cls.dealer, actor=cls.users['owner'],
            entry_id=cls.cost.pk, reason='Corrected synthetic invoice amount', request_key=uuid4(),
        )
        cls.replacement_cost = add_cost(
            vehicle_id=cls.vehicle.pk, dealership=cls.dealer, actor=cls.users['owner'],
            data={
                'request_key': uuid4(), 'category': 'parts', 'description': 'Corrected tire set',
                'amount': Decimal('395.00'), 'effective_on': date(2026, 10, 2),
                'vendor': cls.vendor, 'new_vendor': '', 'task': cls.task,
            },
        )
        add_cost(
            vehicle_id=cls.foreign_vehicle.pk, dealership=cls.other, actor=cls.users['foreign'],
            data={
                'request_key': uuid4(), 'category': 'repair', 'description': 'FOREIGN-PRIVATE-COST',
                'amount': Decimal('999.00'), 'effective_on': timezone.localdate(),
                'vendor': foreign_vendor, 'new_vendor': '', 'task': None,
            },
        )
        AuditEvent.objects.create(
            dealership=cls.other, actor=cls.users['foreign'], vehicle=cls.foreign_vehicle,
            action='created', changes={'notes': {'before': None, 'after': 'FOREIGN-PRIVATE-AUDIT'}},
        )

    def setUp(self):
        temporary = TemporaryDirectory()
        self.media = Path(temporary.name)
        self.addCleanup(temporary.cleanup)
        override = self.settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)

        prepared = [normalize_photo(photo_file(color='blue')), normalize_photo(photo_file(color='green'))]
        self.active_photo, self.archived_photo = add_photos(self.vehicle, prepared, actor=self.users['staff'])
        change_photo(self.archived_photo, 'hide', actor=self.users['owner'])
        self.archived_photo.refresh_from_db()
        self.foreign_photo = add_photos(
            self.foreign_vehicle, [normalize_photo(photo_file(color='red'))], actor=self.users['foreign'],
        )[0]

    def export(self, actor=None, dealer=None):
        return export_inventory(dealership_id=(dealer or self.dealer).pk, actor=actor or self.users['owner'])

    def test_inventory_records_reversals_photo_bytes_and_history_are_scoped(self):
        data = self.export()
        json_meta = {k: v for k, v in data.items() if k != 'photo_artifacts'}
        serialized = json.dumps(json_meta)
        self.assertEqual(data['format'], FORMAT_VERSION)
        self.assertTrue(data['synthetic_only'])
        self.assertEqual(data['dealership_id'], self.dealer.pk)
        self.assertEqual(data['exported_by_user_id'], self.users['owner'].pk)
        self.assertIn('not guaranteed', data['consistency'])
        self.assertIn('Not a complete dealership backup', data['scope'])
        self.assertNotIn('FOREIGN-', serialized)

        # Vehicles preserve exact decimals, dates, and nulls
        self.assertEqual({v['id'] for v in data['vehicles']}, {self.vehicle.pk, self.unpriced_vehicle.pk})
        veh = next(v for v in data['vehicles'] if v['id'] == self.vehicle.pk)
        self.assertEqual(veh['acquired_on'], '2026-09-01')
        self.assertEqual(veh['sold_on'], '2026-10-15')
        self.assertEqual(veh['acquisition_cost'], '5000.10')
        self.assertEqual(veh['recon_cost'], '100.20')
        self.assertEqual(veh['asking_price'], '6995.00')
        self.assertEqual(veh['notes'], '=synthetic note')

        # Active and archived photos both include verified original and thumbnail bytes + hashes
        self.assertEqual([p['id'] for p in data['photos']], [self.active_photo.pk, self.archived_photo.pk])
        self.assertIsNone(data['photos'][0]['archived_at'])
        self.assertIsNotNone(data['photos'][1]['archived_at'])
        self.assertEqual(len(data['photo_artifacts']), 4)
        for p_row, model_obj in zip(data['photos'], (self.active_photo, self.archived_photo)):
            img_id = p_row['image_artifact_id']
            thm_id = p_row['thumbnail_artifact_id']
            self.assertEqual(img_id, f'photos/photo-{model_obj.pk}-image.jpg')
            self.assertEqual(thm_id, f'photos/photo-{model_obj.pk}-thumbnail.jpg')
            with model_obj.image.open('rb') as f:
                expected_img = f.read()
            with model_obj.thumbnail.open('rb') as f:
                expected_thm = f.read()
            self.assertEqual(data['photo_artifacts'][img_id], expected_img)
            self.assertEqual(data['photo_artifacts'][thm_id], expected_thm)
            self.assertEqual(p_row['image_sha256'], hashlib.sha256(expected_img).hexdigest())
            self.assertEqual(p_row['thumbnail_sha256'], hashlib.sha256(expected_thm).hexdigest())
            self.assertEqual(p_row['digest_basis'], 'calculated_at_export_not_stored_at_upload')
            self.assertEqual(p_row['image_bytes'], len(expected_img))
            self.assertEqual(p_row['thumbnail_bytes'], len(expected_thm))
        self.assertIn('do not prove bytes are unchanged since upload', data['scope'])
        self.assertNotIn(f'photos/photo-{self.foreign_photo.pk}-image.jpg', data['photo_artifacts'])

        # Vendors, tasks, costs/reversals, and audit events
        self.assertEqual([v['id'] for v in data['vendors']], [self.vendor.pk])
        self.assertEqual([e['action'] for e in data['vendor_events']], ['created', 'updated'])
        self.assertEqual([t['id'] for t in data['tasks']], [self.task.pk])
        self.assertEqual([c['id'] for c in data['cost_entries']], [self.cost.pk, self.reversal.pk, self.replacement_cost.pk])
        self.assertEqual(len(data['audit_events']), 7)
        self.assertEqual(set(data['audit_events'][0]), {field.attname for field in AuditEvent._meta.concrete_fields})

    def assert_mismatched_audit_fails_for_affected_dealers(self, *, dealer, vehicle, actor):
        event = legacy_mismatch_fixture(dealership=dealer, vehicle=vehicle, actor=actor,
            action='synthetic mismatch', changes={'private': 'MISMATCH-PRIVATE-CONTENT'})
        before = AuditEvent.objects.filter(pk=event.pk).values().get()
        for selected, owner in ((self.dealer, self.users['owner']), (self.other, self.users['foreign'])):
            with self.subTest(dealership=selected.pk), patch('inventory.export._read_verified_jpeg', side_effect=AssertionError('Must not read photos')):
                with self.assertRaises(InventoryExportError) as error:
                    self.export(actor=owner, dealer=selected)
                self.assertEqual(str(error.exception), 'An inventory audit reference is inconsistent; no data returned.')
                self.assertNotIn('MISMATCH-PRIVATE-CONTENT', str(error.exception))
        self.assertEqual(AuditEvent.objects.filter(pk=event.pk).values().get(), before)

        unrelated = Dealership.objects.create(name='Unrelated synthetic dealership')
        owner = get_user_model().objects.create_user(username='unrelated-audit-owner')
        Membership.objects.create(user=owner, dealership=unrelated, role='owner')
        data = self.export(actor=owner, dealer=unrelated)
        self.assertEqual(data['audit_events'], [])
        self.assertNotIn('MISMATCH-PRIVATE-CONTENT', json.dumps(data))
        with self.assertRaises(PermissionDenied):
            self.export(actor=self.users['staff'], dealer=self.dealer)

    def test_local_audit_for_foreign_vehicle_fails_for_both_dealerships(self):
        self.assert_mismatched_audit_fails_for_affected_dealers(
            dealer=self.dealer, vehicle=self.foreign_vehicle, actor=self.users['owner'])

    def test_foreign_audit_for_local_vehicle_fails_for_both_dealerships(self):
        self.assert_mismatched_audit_fails_for_affected_dealers(
            dealer=self.other, vehicle=self.vehicle, actor=self.users['foreign'])

    def test_missing_corrupt_or_out_of_scope_photo_files_abort_entire_export(self):
        # 1. Corrupt bytes on disk
        img_path = Path(self.active_photo.image.path)
        original_bytes = img_path.read_bytes()
        img_path.write_bytes(b'corrupt-not-a-jpeg')
        with self.assertRaises(InventoryPhotoArtifactError):
            self.export()

        # 2. Valid JPEG header but truncated/corrupt body
        img_path.write_bytes(b'\xff\xd8\xff\xe0truncated')
        with self.assertRaises(InventoryPhotoArtifactError):
            self.export()

        # 3. Missing file on disk
        img_path.unlink()
        with self.assertRaises(InventoryPhotoArtifactError):
            self.export()

        # Restore valid bytes, then test out-of-scope database path
        img_path.write_bytes(original_bytes)
        original_image_name = self.active_photo.image.name
        VehiclePhoto.objects.filter(pk=self.active_photo.pk).update(image='other/outside-scope.jpg')
        with self.assertRaises(InventoryPhotoArtifactError):
            self.export()
        VehiclePhoto.objects.filter(pk=self.active_photo.pk).update(image=original_image_name)

        # 4. Path referenced by another dealership's VehiclePhoto (image or thumbnail) is rejected
        for field_name, foreign_path in (
            ('image', self.foreign_photo.image.name),
            ('image', self.foreign_photo.thumbnail.name),
            ('thumbnail', self.foreign_photo.image.name),
            ('thumbnail', self.foreign_photo.thumbnail.name),
        ):
            with self.subTest(field=field_name, foreign_path=foreign_path):
                VehiclePhoto.objects.filter(pk=self.active_photo.pk).update(**{field_name: foreign_path})
                with self.assertRaises(InventoryPhotoArtifactError):
                    self.export()
        VehiclePhoto.objects.filter(pk=self.active_photo.pk).update(
            image=original_image_name, thumbnail=self.active_photo.thumbnail.name,
        )

        # 5. Symlinked photo file is rejected before resolving
        backup_path = img_path.with_name('backup-' + img_path.name)
        img_path.rename(backup_path)
        img_path.symlink_to(backup_path)
        with self.assertRaises(InventoryPhotoArtifactError):
            self.export()
        img_path.unlink()
        backup_path.rename(img_path)

    def test_owner_only_and_dealership_scope(self):
        for actor in (self.users['staff'], self.users['viewer'], self.users['foreign'], AnonymousUser()):
            with self.subTest(actor=str(actor)), self.assertRaises(PermissionDenied):
                self.export(actor=actor)
        with self.assertRaises(PermissionDenied):
            self.export(dealer=self.other)
        self.users['owner'].is_active = False
        self.users['owner'].save(update_fields=['is_active'])
        with self.assertRaises(PermissionDenied):
            self.export()

    def test_synthetic_gates(self):
        for overrides in ({'DEBUG': False}, {'RECON_DEMO_ENABLED': False}):
            with self.subTest(overrides=overrides), override_settings(**overrides), self.assertRaises(PermissionDenied):
                self.export()

    def test_excess_records_or_photo_bytes_fail_without_partial_result(self):
        for limit in (
            'MAX_VEHICLES', 'MAX_PHOTOS', 'MAX_VENDORS', 'MAX_VENDOR_EVENTS',
            'MAX_TASKS', 'MAX_COSTS', 'MAX_AUDIT_EVENTS', 'MAX_TOTAL_PHOTO_BYTES', 'MAX_PHOTO_BYTES',
        ):
            with self.subTest(limit=limit), patch('inventory.export.' + limit, 0), self.assertRaises(InventoryExportTooLarge):
                self.export()

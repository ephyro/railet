# SPDX-License-Identifier: MPL-2.0
import hashlib
import io
import json
import tempfile
import zipfile
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import DatabaseError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from customers.models import Customer, CustomerExportEvent
from deals.models import DraftDeal
from documents.models import DealFile
from feedback.models import FeedbackReport
from finance.services import open_book
from inventory.models import Vehicle
from inventory.photos import add_photos, normalize_photo
from inventory.test_photos import photo_file
from .models import AuditEvent, Dealership, DealershipExportEvent, Membership, SavedView
from .test_audit_guards import legacy_mismatch_fixture

PDF = b'%PDF-1.7\nSynthetic private document\n%%EOF\n'


@override_settings(DEBUG=True, CUSTOMER_ACTIVITY_DEMO_ENABLED=True, RECON_DEMO_ENABLED=True,
                   DEMO_COMPLETION_ENABLED=True, DEMO_PACKETS_ENABLED=True, DEAL_FILES_DEMO_ENABLED=True,
                   DEMO_LEDGER_ENABLED=True, DEMO_SERVICING_ENABLED=True)
class DealershipPackageTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        override = override_settings(MEDIA_ROOT=temp.name)
        override.enable()
        self.addCleanup(override.disable)
        self.dealer = Dealership.objects.create(name='Synthetic dealership')
        self.other = Dealership.objects.create(name='Other dealership')
        self.users = {}
        for name, role, dealer in [('owner','owner',self.dealer), ('staff','staff',self.dealer),
                                   ('viewer','viewer',self.dealer), ('foreign','owner',self.other)]:
            user = get_user_model().objects.create_user('package-'+name, password='SYNTHETIC-SECRET-PASSWORD', email='private-email@example.invalid')
            Membership.objects.create(user=user, dealership=dealer, role=role)
            self.users[name] = user
        self.customer = Customer.objects.create(dealership=self.dealer, first_name='Synthetic', last_name='Buyer')
        self.vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='SYNTHETIC-STOCK', year=2020, make='Demo', model='Sedan')
        self.deal = DraftDeal.objects.create(dealership=self.dealer, buyer=self.customer, vehicle=self.vehicle)
        self.photo = add_photos(self.vehicle, [normalize_photo(photo_file(color='blue'))], actor=self.users['staff'])[0]
        self.file = DealFile.objects.create(deal=self.deal, title='Synthetic PDF', blob=ContentFile(PDF, name='example.pdf'),
            sha256=hashlib.sha256(PDF).hexdigest(), byte_size=len(PDF), created_by=self.users['staff'])
        open_book(dealership_id=self.dealer.pk, customer_id=self.customer.pk, actor=self.users['staff'],
            label='Synthetic account', source_reference='Invented', opening_on=timezone.localdate(), opening_amount='1000.25', request_key=uuid4())
        FeedbackReport.objects.create(dealership=self.dealer, author=self.users['staff'], kind='idea', area='general',
            subject='Synthetic feedback', expected='Expected', actual='Actual')
        SavedView.objects.create(dealership=self.dealer, owner=self.users['owner'], resource='inventory', name='SECRET-SAVED-VIEW', parameters={})
        foreign_customer = Customer.objects.create(dealership=self.other, first_name='FOREIGN-PRIVATE')
        self.foreign_vehicle = Vehicle.objects.create(dealership=self.other, stock_number='FOREIGN-PRIVATE', year=2020, make='Other', model='Car')
        DraftDeal.objects.create(dealership=self.other, buyer=foreign_customer, vehicle=self.foreign_vehicle, notes='FOREIGN-PRIVATE')
        self.client.force_login(self.users['owner'])
        self.review = reverse('dealership_export_review')
        self.download = reverse('dealership_export_download')
        self.token = self.client.get(self.review).context['export_token']

    def post_download(self, data=None):
        return self.client.post(self.download, {'export_token': self.token, **(data or {})})

    def test_review_and_download_package_content_and_hash_manifest(self):
        page = self.client.get(self.review)
        self.assertContains(page, 'not a complete backup')
        self.assertContains(page, 'not encrypted')
        self.assertContains(page, 'not guaranteed')
        self.assertFalse(DealershipExportEvent.objects.exists())
        response = self.post_download({'dealership_id': self.other.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('attachment', response['Content-Disposition'])
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = set(archive.namelist())
            self.assertTrue({'foundation.json','customers.json','inventory.json','deals.json','documents.zip','finance.json','feedback.json','manifest.json'} <= names)
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['dealership_id'], self.dealer.pk)
            self.assertEqual(set(manifest['files']), names - {'manifest.json'})
            for name, entry in manifest['files'].items():
                data = archive.read(name)
                self.assertEqual(entry['sha256'], hashlib.sha256(data).hexdigest())
                self.assertEqual(entry['bytes'], len(data))
            inventory = json.loads(archive.read('inventory.json'))
            photo = inventory['photos'][0]
            with self.photo.image.open('rb') as original:
                self.assertEqual(archive.read('inventory/' + photo['image_artifact_id']), original.read())
            with zipfile.ZipFile(io.BytesIO(archive.read('documents.zip'))) as documents:
                self.assertEqual(documents.read(f'deal-files/{self.file.pk}.pdf'), PDF)
            self.assertEqual(json.loads(archive.read('finance.json'))['postings'][0]['amount_cents'], 100025)
            self.assertEqual(json.loads(archive.read('feedback.json'))['reports'][0]['subject'], 'Synthetic feedback')
            for name in names:
                if name.endswith('.json'):
                    raw = archive.read(name).decode()
                    self.assertNotIn('FOREIGN-PRIVATE', raw)
                    self.assertNotIn('SECRET-SAVED-VIEW', raw)
                    self.assertNotIn('SYNTHETIC-SECRET-PASSWORD', raw)
                    self.assertNotIn(self.users['owner'].password, raw)
                    self.assertNotIn('private-email@example.invalid', raw)
        event = DealershipExportEvent.objects.get()
        self.assertEqual((event.actor_id, event.dealership_id), (self.users['owner'].pk, self.dealer.pk))
        self.assertEqual(event.sha256, hashlib.sha256(response.content).hexdigest())
        self.assertEqual(event.byte_size, len(response.content))

    def test_package_preserves_prior_export_audits_without_its_own_event(self):
        foreign = DealershipExportEvent.objects.create(dealership=self.other, actor=self.users['foreign'],
            format_version='FOREIGN-PACKAGE', sha256='f' * 64, byte_size=111)
        first = self.post_download()
        self.assertEqual(first.status_code, 200)
        first_event = DealershipExportEvent.objects.get(dealership=self.dealer)
        with zipfile.ZipFile(io.BytesIO(first.content)) as archive:
            foundation = json.loads(archive.read('foundation.json'))
            self.assertEqual(foundation['dealership_export_events'], [])
        second = self.post_download()
        self.assertEqual(second.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(second.content)) as archive:
            raw = archive.read('foundation.json')
            foundation = json.loads(raw)
            self.assertEqual(foundation['format'], 'railet-synthetic-foundation-v2')
            self.assertEqual([row['id'] for row in foundation['dealership_export_events']], [first_event.pk])
            self.assertEqual(foundation['dealership_export_events'][0]['sha256'], hashlib.sha256(first.content).hexdigest())
            self.assertNotIn(foreign.format_version, raw.decode())
            self.assertEqual(json.loads(archive.read('manifest.json'))['files']['foundation.json']['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(DealershipExportEvent.objects.filter(dealership=self.dealer).count(), 2)

    def test_package_contains_only_same_dealership_customer_export_history(self):
        foreign = CustomerExportEvent.objects.create(dealership=self.other, actor=self.users['foreign'],
            format_version='FOREIGN-PRIVATE-FORMAT', sha256='f' * 64, byte_size=111)
        customer_download = self.client.post(reverse('customer_export_download'))
        self.assertEqual(customer_download.status_code, 200)
        event = CustomerExportEvent.objects.get(dealership=self.dealer)
        package = self.post_download()
        self.assertEqual(package.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
            raw = archive.read('customers.json')
            data = json.loads(raw)
            self.assertEqual(data['format'], 'railet-synthetic-customers-v3')
            self.assertEqual([row['id'] for row in data['customer_export_events']], [event.pk])
            self.assertEqual(data['customer_export_events'][0]['sha256'], hashlib.sha256(customer_download.content).hexdigest())
            self.assertNotIn(foreign.format_version, raw.decode())
            self.assertEqual(json.loads(archive.read('manifest.json'))['files']['customers.json']['sha256'], hashlib.sha256(raw).hexdigest())
        with patch('customers.export.MAX_EXPORT_EVENTS', 0):
            failed = self.post_download()
        self.assertEqual(failed.status_code, 409)
        self.assertNotIn('Content-Disposition', failed)
        self.assertEqual(DealershipExportEvent.objects.filter(dealership=self.dealer).count(), 1)

    def test_export_audit_limit_fails_without_partial_package_or_new_event(self):
        event = DealershipExportEvent.objects.create(dealership=self.dealer, actor=self.users['owner'],
            format_version='synthetic-v1', sha256='a' * 64, byte_size=123)
        with patch('core.export.MAX_EXPORT_EVENTS', 0):
            response = self.post_download()
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('Content-Disposition', response)
        self.assertEqual(list(DealershipExportEvent.objects.values_list('pk', flat=True)), [event.pk])

    def assert_mismatched_inventory_audit_blocks_both_packages(self, *, dealer, vehicle, actor):
        event = legacy_mismatch_fixture(dealership=dealer, vehicle=vehicle, actor=actor,
            action='synthetic mismatch', changes={'private': 'MISMATCH-PRIVATE-CONTENT'})
        before = AuditEvent.objects.filter(pk=event.pk).values().get()
        for user in ('owner', 'foreign'):
            with self.subTest(user=user):
                self.client.force_login(self.users[user])
                token = self.client.get(self.review).context['export_token']
                response = self.client.post(self.download, {'export_token': token})
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response['Cache-Control'], 'private, no-store')
                self.assertNotIn('Content-Disposition', response)
                self.assertNotIn(b'MISMATCH-PRIVATE-CONTENT', response.content)
                self.assertNotIn(b'FOREIGN-PRIVATE', response.content)
        self.assertFalse(DealershipExportEvent.objects.exists())
        self.assertEqual(AuditEvent.objects.filter(pk=event.pk).values().get(), before)

    def test_package_rejects_local_audit_for_foreign_vehicle(self):
        self.assert_mismatched_inventory_audit_blocks_both_packages(
            dealer=self.dealer, vehicle=self.foreign_vehicle, actor=self.users['owner'])

    def test_package_rejects_foreign_audit_for_local_vehicle(self):
        self.assert_mismatched_inventory_audit_blocks_both_packages(
            dealer=self.other, vehicle=self.vehicle, actor=self.users['foreign'])

    def test_roles_gates_csrf_and_cross_dealership(self):
        for name in ('staff','viewer'):
            self.client.force_login(self.users[name])
            self.assertEqual(self.client.get(self.review).status_code, 403)
            self.assertEqual(self.post_download().status_code, 403)
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.post_download().status_code, 403)
        self.token = self.client.get(self.review).context['export_token']
        response = self.post_download({'dealership_id': self.dealer.pk})
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(json.loads(archive.read('manifest.json'))['dealership_id'], self.other.pk)
            self.assertNotIn('SYNTHETIC-STOCK', archive.read('inventory.json').decode())
        self.client.force_login(self.users['owner'])
        with override_settings(DEMO_LEDGER_ENABLED=False):
            self.assertEqual(self.client.get(self.review).status_code, 403)
            self.assertEqual(self.post_download().status_code, 403)
        self.assertEqual(self.client.get(self.download).status_code, 405)
        strict = Client(enforce_csrf_checks=True); strict.force_login(self.users['owner'])
        self.assertEqual(strict.post(self.download).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.review).status_code, 302)

    def test_role_or_dealership_change_after_review_blocks_download_before_file_reads(self):
        membership = Membership.objects.get(user=self.users['owner'])
        with patch('documents.export._artifact', side_effect=AssertionError('Unauthorized file read')):
            membership.role = 'staff'
            membership.save(update_fields=['role'])
            self.assertEqual(self.post_download().status_code, 403)
            membership.role = 'owner'
            membership.dealership = self.other
            membership.save(update_fields=['role', 'dealership'])
            self.assertEqual(self.post_download().status_code, 403)
        self.assertFalse(DealershipExportEvent.objects.exists())

    def test_corrupt_or_missing_components_and_audit_failure_return_no_package(self):
        for target, options in [('core.dealership_export.export_documents', {'return_value': b'broken'}),
                                ('core.dealership_export.MAX_TOTAL_BYTES', {'new': 1})]:
            with self.subTest(target=target), patch(target, **options):
                response = self.post_download()
                self.assertEqual(response.status_code, 409)
                self.assertNotIn('Content-Disposition', response)
        self.file.blob.delete(save=False)
        response = self.post_download()
        self.assertEqual(response.status_code, 409)
        self.file.blob.save('restored.pdf', ContentFile(PDF), save=True)
        with patch('core.dealership_export_views.DealershipExportEvent.objects.create', side_effect=DatabaseError('synthetic failure')):
            response = self.post_download()
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('Content-Disposition', response)
        self.assertFalse(DealershipExportEvent.objects.exists())

    def test_audit_guard_rejects_updates_deletes_and_foreign_actor(self):
        self.assertEqual(self.post_download().status_code, 200)
        event = DealershipExportEvent.objects.get()
        for action in ('update', 'delete'):
            with self.subTest(action=action), self.assertRaises(DatabaseError), transaction.atomic():
                query = DealershipExportEvent.objects.filter(pk=event.pk)
                query.update(sha256='changed') if action == 'update' else query.delete()
        with self.assertRaises(DatabaseError), transaction.atomic():
            DealershipExportEvent.objects.create(dealership=self.dealer, actor=self.users['foreign'], format_version='test', sha256='0'*64, byte_size=1)

    def test_review_token_and_corrupt_photo_fail_without_audit(self):
        response = self.post_download({'export_token': self.token + 'tampered'})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('Content-Disposition', response)
        with self.photo.image.open('wb') as image:
            image.write(b'not a jpeg')
        response = self.post_download()
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('Content-Disposition', response)
        self.assertFalse(DealershipExportEvent.objects.exists())

    def test_foreign_private_file_path_aliases_are_rejected(self):
        foreign_vehicle = Vehicle.objects.create(dealership=self.other, stock_number='FOREIGN-FILE',
                                                  year=2022, make='Synthetic', model='Other')
        foreign_buyer = Customer.objects.create(dealership=self.other, first_name='Other')
        foreign_deal = DraftDeal.objects.create(dealership=self.other, buyer=foreign_buyer, vehicle=foreign_vehicle)
        foreign_pdf = b'%PDF-1.7\nOther dealership private synthetic file\n%%EOF\n'
        foreign_file = DealFile.objects.create(deal=foreign_deal, title='Foreign synthetic',
            blob=ContentFile(foreign_pdf, name='foreign.pdf'), sha256=hashlib.sha256(foreign_pdf).hexdigest(),
            byte_size=len(foreign_pdf), created_by=self.users['foreign'])
        original_name = self.file.blob.name
        alias = foreign_file.blob.name.replace('deal-files/', 'deal-files/./', 1)
        DealFile.objects.filter(pk=self.file.pk).update(blob=alias, sha256=foreign_file.sha256, byte_size=len(foreign_pdf))
        response = self.post_download()
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('Content-Disposition', response)
        self.assertFalse(DealershipExportEvent.objects.exists())
        DealFile.objects.filter(pk=self.file.pk).update(blob=foreign_file.blob.name)
        DealFile.objects.filter(pk=foreign_file.pk).update(blob=alias)
        response = self.post_download()
        self.assertEqual(response.status_code, 409)
        self.assertFalse(DealershipExportEvent.objects.exists())

        DealFile.objects.filter(pk=self.file.pk).update(blob=original_name, sha256=hashlib.sha256(PDF).hexdigest(), byte_size=len(PDF))
        foreign_photo = add_photos(foreign_vehicle, [normalize_photo(photo_file(color='red'))], actor=self.users['foreign'])[0]
        alias = foreign_photo.image.name.replace('vehicles/', 'vehicles/./', 1)
        from inventory.models import VehiclePhoto
        VehiclePhoto.objects.filter(pk=self.photo.pk).update(image=alias)
        response = self.post_download()
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('Content-Disposition', response)
        self.assertFalse(DealershipExportEvent.objects.exists())
        VehiclePhoto.objects.filter(pk=self.photo.pk).update(image=foreign_photo.image.name)
        VehiclePhoto.objects.filter(pk=foreign_photo.pk).update(image=alias)
        response = self.post_download()
        self.assertEqual(response.status_code, 409)
        self.assertFalse(DealershipExportEvent.objects.exists())

    def test_owner_navigation_and_individual_synthetic_gates(self):
        self.assertContains(self.client.get(reverse('customers')), self.review)
        self.client.force_login(self.users['viewer'])
        self.assertNotContains(self.client.get(reverse('customers')), self.review)
        self.client.force_login(self.users['owner'])
        for flag in ('DEBUG', 'CUSTOMER_ACTIVITY_DEMO_ENABLED', 'RECON_DEMO_ENABLED',
                     'DEMO_COMPLETION_ENABLED', 'DEMO_PACKETS_ENABLED', 'DEAL_FILES_DEMO_ENABLED',
                     'DEMO_LEDGER_ENABLED', 'DEMO_SERVICING_ENABLED'):
            with self.subTest(flag=flag), override_settings(**{flag: False}):
                self.assertEqual(self.client.get(self.review).status_code, 403)
                self.assertEqual(self.post_download().status_code, 403)
        self.assertFalse(DealershipExportEvent.objects.exists())

    def test_package_contains_only_scoped_mock_history_when_simulator_disabled(self):
        from customers.message_simulator import submit_mock, record_mock_event
        with override_settings(DEMO_MESSAGE_SIMULATOR_ENABLED=True):
            key = uuid4()
            submission, _ = submit_mock(dealership_id=self.dealer.pk, actor=self.users['staff'], submission_id=key,
                recipient_label='mock-recipient-alpha', scenario='mock-follow-up')
            event, _ = record_mock_event(dealership_id=self.dealer.pk, actor=self.users['staff'], submission_id=key,
                event_id=uuid4(), label='mock-accepted')
            foreign_key = uuid4()
            submit_mock(dealership_id=self.other.pk, actor=self.users['foreign'], submission_id=foreign_key,
                recipient_label='mock-recipient-beta', scenario='mock-appointment')
            record_mock_event(dealership_id=self.other.pk, actor=self.users['foreign'], submission_id=foreign_key,
                event_id=uuid4(), label='mock-failed')
        with override_settings(DEMO_MESSAGE_SIMULATOR_ENABLED=False):
            response = self.post_download()
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            raw = archive.read('customers.json')
            data = json.loads(raw)
            self.assertEqual(data['format'], 'railet-synthetic-customers-v3')
            self.assertEqual([r['id'] for r in data['mock_message_submissions']], [submission.pk])
            self.assertEqual([r['id'] for r in data['mock_message_events']], [event.pk])
            self.assertNotIn(str(foreign_key), raw.decode())
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['files']['customers.json']['sha256'], hashlib.sha256(raw).hexdigest())

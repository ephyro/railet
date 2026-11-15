# SPDX-License-Identifier: MPL-2.0
import hashlib
import io
import json
import tempfile
import zipfile
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from core.models import Dealership, Membership
from customers.models import Customer
from deals.models import DraftDeal
from inventory.models import Vehicle, VehicleCostEntry
from .export import DocumentsExportError, FORMAT_VERSION, export_documents
from .models import (DealFile, DealFileEvent, DemoDealPacket, DemoPacketExportEvent,
                     VehicleAcquisitionFile, VehicleAcquisitionFileEvent,
                     VehicleInvoice, VehicleInvoiceEvent)
from .packets import digest, source_digest

PDF = b'%PDF-1.7\nSynthetic supporting document\n%%EOF\n'
INVOICE = b'%PDF-1.7\nSynthetic vendor invoice\n%%EOF\n'
ACQUISITION = b'%PDF-1.7\nSynthetic acquisition attachment\n%%EOF\n'
HTML = '<!doctype html><p>Synthetic demo only</p>'


@override_settings(DEBUG=True, DEAL_FILES_DEMO_ENABLED=True, DEMO_PACKETS_ENABLED=True, RECON_DEMO_ENABLED=True)
class DocumentsExportTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.temp.name)
        self.override.enable()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.override.disable)
        self.dealer = Dealership.objects.create(name='Synthetic documents dealer')
        self.other = Dealership.objects.create(name='Other dealer')
        self.users = {}
        for label, role, dealer in [('owner','owner',self.dealer), ('staff','staff',self.dealer),
                                    ('viewer','viewer',self.dealer), ('foreign','owner',self.other)]:
            user = get_user_model().objects.create_user('documents-export-' + label)
            Membership.objects.create(user=user, dealership=dealer, role=role)
            self.users[label] = user
        self.vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='SYN', year=2020, make='Demo', model='Car')
        self.buyer = Customer.objects.create(dealership=self.dealer, first_name='Synthetic', last_name='Buyer')
        self.deal = DraftDeal.objects.create(dealership=self.dealer, vehicle=self.vehicle, buyer=self.buyer)
        self.file = DealFile.objects.create(deal=self.deal, title='Synthetic archived file', blob=ContentFile(PDF, name='synthetic.pdf'),
            sha256=hashlib.sha256(PDF).hexdigest(), byte_size=len(PDF), created_by=self.users['staff'], archived_at=timezone.now())
        self.file_event = DealFileEvent.objects.create(file=self.file, actor=self.users['staff'], action='archive', reason='Synthetic')
        snapshot = {'schema_version': 5, 'unknown': None, 'synthetic': 'preserved'}
        self.packet = DemoDealPacket.objects.create(deal=self.deal, created_by=self.users['staff'], created_at=timezone.now(),
            creation_key=uuid4(), template_version='synthetic-v1', snapshot=snapshot, source_sha256=source_digest(snapshot),
            html=HTML, artifact_sha256=digest(HTML))
        self.packet_event = DemoPacketExportEvent.objects.create(packet=self.packet, actor=self.users['staff'], bundle_sha256='1'*64)
        self.cost = VehicleCostEntry.objects.create(vehicle=self.vehicle, kind='cost', category='repair', description='Synthetic',
            amount_cents=100, effective_on=timezone.localdate(), actor=self.users['staff'])
        self.invoice = VehicleInvoice.objects.create(vehicle=self.vehicle, cost=self.cost, title='Synthetic invoice',
            blob=ContentFile(INVOICE, name='synthetic.pdf'), sha256=hashlib.sha256(INVOICE).hexdigest(),
            byte_size=len(INVOICE), created_by=self.users['staff'])
        self.invoice_event = VehicleInvoiceEvent.objects.create(invoice=self.invoice, actor=self.users['staff'], action='upload')
        self.acquisition_file = VehicleAcquisitionFile.objects.create(
            vehicle=self.vehicle, title='Synthetic bill of sale', description='Unverified auction PDF',
            blob=ContentFile(ACQUISITION, name='synthetic-acq.pdf'), sha256=hashlib.sha256(ACQUISITION).hexdigest(),
            byte_size=len(ACQUISITION), created_by=self.users['staff'], archived_at=timezone.now(),
        )
        self.acquisition_event = VehicleAcquisitionFileEvent.objects.create(
            file=self.acquisition_file, actor=self.users['staff'], action='archive', reason='Synthetic archive',
        )
        self.foreign_vehicle = Vehicle.objects.create(dealership=self.other, stock_number='FOREIGN', year=2020, make='Other', model='Car')
        self.foreign_customer = Customer.objects.create(dealership=self.other, first_name='Other')
        self.foreign_deal = DraftDeal.objects.create(dealership=self.other, vehicle=self.foreign_vehicle, buyer=self.foreign_customer)
        self.foreign_file = DealFile.objects.create(deal=self.foreign_deal, title='FOREIGN-SECRET',
            blob=ContentFile(b'FOREIGN-SECRET', name='foreign.pdf'), sha256='0'*64, byte_size=14, created_by=self.users['foreign'])

    def export(self, actor=None, dealership_id=None):
        return export_documents(dealership_id=dealership_id or self.dealer.pk, actor=actor or self.users['owner'])

    def test_scoped_archive_contains_all_metadata_histories_and_verified_bytes(self):
        archive = zipfile.ZipFile(io.BytesIO(self.export()))
        names = set(archive.namelist())
        file_name = f'deal-files/{self.file.pk}.pdf'
        invoice_name = f'vehicle-invoices/{self.invoice.pk}.pdf'
        acquisition_name = f'vehicle-acquisition/{self.acquisition_file.pk}.pdf'
        packet_name = f'packets/{self.packet.pk}.html'
        self.assertEqual(names, {'metadata.json', 'manifest.json', file_name, invoice_name, acquisition_name, packet_name})
        self.assertEqual(archive.read(file_name), PDF)
        self.assertEqual(archive.read(invoice_name), INVOICE)
        self.assertEqual(archive.read(acquisition_name), ACQUISITION)
        self.assertEqual(archive.read(packet_name), HTML.encode())
        meta = json.loads(archive.read('metadata.json'))
        self.assertEqual(meta['format'], FORMAT_VERSION)
        self.assertEqual(meta['deal_files'][0]['id'], self.file.pk)
        self.assertIsNotNone(meta['deal_files'][0]['archived_at'])
        self.assertEqual(meta['deal_file_events'][0]['reason'], 'Synthetic')
        self.assertEqual(meta['packets'][0]['snapshot'], self.packet.snapshot)
        self.assertEqual(meta['packets'][0]['template_version'], 'synthetic-v1')
        self.assertEqual(meta['packet_export_events'][0]['id'], self.packet_event.pk)
        self.assertEqual(meta['vehicle_invoices'][0]['cost_id'], self.cost.pk)
        self.assertEqual(meta['vehicle_invoice_events'][0]['id'], self.invoice_event.pk)
        self.assertEqual(meta['vehicle_acquisition_files'][0]['id'], self.acquisition_file.pk)
        self.assertEqual(meta['vehicle_acquisition_files'][0]['description'], 'Unverified auction PDF')
        self.assertIsNotNone(meta['vehicle_acquisition_files'][0]['archived_at'])
        self.assertEqual(meta['vehicle_acquisition_file_events'][0]['id'], self.acquisition_event.pk)
        for model, key, extra, omit in (
            (DealFile, 'deal_files', {'artifact'}, set()),
            (DealFileEvent, 'deal_file_events', set(), set()),
            (DemoDealPacket, 'packets', {'artifact'}, {'html'}),
            (DemoPacketExportEvent, 'packet_export_events', set(), set()),
            (VehicleInvoice, 'vehicle_invoices', {'artifact'}, set()),
            (VehicleInvoiceEvent, 'vehicle_invoice_events', set(), set()),
            (VehicleAcquisitionFile, 'vehicle_acquisition_files', {'artifact'}, set()),
            (VehicleAcquisitionFileEvent, 'vehicle_acquisition_file_events', set(), set()),
        ):
            with self.subTest(model=model.__name__):
                fields = {f.attname for f in model._meta.concrete_fields if f.name not in omit}
                self.assertEqual(set(meta[key][0]), fields | extra)
        self.assertNotIn('FOREIGN-SECRET', archive.read('metadata.json').decode())
        self.assertIn('not a guaranteed', meta['consistency'])
        manifest = json.loads(archive.read('manifest.json'))
        for name, info in manifest['files'].items():
            data = archive.read(name)
            self.assertEqual(info['bytes'], len(data))
            self.assertEqual(info['sha256'], hashlib.sha256(data).hexdigest())

    def test_authentication_and_gates_precede_opening_any_artifact(self):
        with patch('documents.export._artifact', side_effect=AssertionError('must not open')):
            for actor in (self.users['staff'], self.users['viewer'], self.users['foreign'], AnonymousUser()):
                with self.subTest(actor=str(actor)), self.assertRaises(PermissionDenied): self.export(actor=actor)
            for gate in ('DEBUG', 'DEAL_FILES_DEMO_ENABLED', 'DEMO_PACKETS_ENABLED', 'RECON_DEMO_ENABLED'):
                with self.subTest(gate=gate), override_settings(**{gate:False}), self.assertRaises(PermissionDenied): self.export()
            with self.assertRaises(PermissionDenied): self.export(dealership_id=self.other.pk)
            self.users['owner'].is_active = False; self.users['owner'].save(update_fields=['is_active'])
            with self.assertRaises(PermissionDenied): self.export()

    def test_missing_and_corrupt_artifacts_fail_without_package(self):
        self.file.blob.delete(save=False)
        with self.assertRaises(DocumentsExportError): self.export()
        self.file.blob.save('replacement.pdf', ContentFile(PDF), save=True)
        VehicleInvoice.objects.filter(pk=self.invoice.pk).update(sha256='0'*64)
        with self.assertRaises(DocumentsExportError): self.export()
        VehicleInvoice.objects.filter(pk=self.invoice.pk).update(sha256=hashlib.sha256(INVOICE).hexdigest())
        DemoDealPacket.objects.filter(pk=self.packet.pk).update(html='altered')
        with self.assertRaises(DocumentsExportError): self.export()
        DemoDealPacket.objects.filter(pk=self.packet.pk).update(html=HTML, snapshot={'altered':True})
        with self.assertRaises(DocumentsExportError): self.export()

    def test_out_of_scope_reference_and_oversize_fail_closed(self):
        other_cost = VehicleCostEntry.objects.create(vehicle=self.foreign_vehicle, kind='cost', category='repair',
            description='Other', amount_cents=1, effective_on=timezone.localdate(), actor=self.users['foreign'])
        VehicleInvoice.objects.filter(pk=self.invoice.pk).update(cost=other_cost)
        with self.assertRaises(DocumentsExportError): self.export()
        VehicleInvoice.objects.filter(pk=self.invoice.pk).update(cost=self.cost)
        with patch('documents.export.MAX_RECORDS', 0), self.assertRaises(DocumentsExportError): self.export()
        with patch('documents.export.MAX_ARTIFACT_BYTES', 1), self.assertRaises(DocumentsExportError): self.export()
        with patch('documents.export.MAX_TOTAL_BYTES', 1), self.assertRaises(DocumentsExportError): self.export()

    def test_shared_foreign_storage_path_is_rejected(self):
        DealFile.objects.filter(pk=self.foreign_file.pk).update(blob=self.file.blob.name)
        with self.assertRaises(DocumentsExportError): self.export()

    def test_invoice_and_acquisition_foreign_path_aliases_fail_in_both_directions(self):
        for model, prefix in (
            (VehicleInvoice, 'vehicle-invoices/'),
            (VehicleAcquisitionFile, 'vehicle-acquisition/'),
        ):
            for alias_local in (True, False):
                with self.subTest(model=model.__name__, alias_local=alias_local), transaction.atomic():
                    storage = model._meta.get_field('blob').storage
                    name = storage.save(f'{prefix}{uuid4()}.pdf', ContentFile(INVOICE))
                    alias = name.replace(prefix, prefix + './', 1)
                    fields = {'title': 'Synthetic alias', 'sha256': hashlib.sha256(INVOICE).hexdigest(),
                              'byte_size': len(INVOICE)}
                    model.objects.create(vehicle=self.foreign_vehicle, blob=name if alias_local else alias,
                                         created_by=self.users['foreign'], **fields)
                    model.objects.create(vehicle=self.vehicle, blob=alias if alias_local else name,
                                         created_by=self.users['staff'], **fields)
                    with self.assertRaises(DocumentsExportError): self.export()
                    transaction.set_rollback(True)

    def test_invalid_storage_path_is_rejected(self):
        DealFile.objects.filter(pk=self.file.pk).update(blob='deal-files/../../outside.pdf')
        with self.assertRaises(DocumentsExportError): self.export()

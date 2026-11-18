# SPDX-License-Identifier: MPL-2.0
import tempfile
import uuid
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import Dealership, Membership
from inventory.models import Vehicle, VehicleCostEntry
from .models import VehicleInvoice, VehicleInvoiceEvent

PDF = b'%PDF-1.7\nSynthetic invoice\n%%EOF\n'


@override_settings(RECON_DEMO_ENABLED=True, DEAL_FILES_DEMO_ENABLED=True)
class InvoiceTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.temp.name)
        self.settings_override.enable()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.settings_override.disable)
        self.dealer = Dealership.objects.create(name='Synthetic')
        self.other = Dealership.objects.create(name='Other')
        self.users = {}
        for name, role, dealer in [('owner', 'owner', self.dealer), ('staff', 'staff', self.dealer), ('viewer', 'viewer', self.dealer), ('foreign', 'owner', self.other)]:
            self.users[name] = get_user_model().objects.create_user(name)
            Membership.objects.create(user=self.users[name], dealership=dealer, role=role)
        self.vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='S1', year=2020, make='Demo', model='Car')
        self.other_vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='S2', year=2020, make='Demo', model='Car')
        self.cost = self.make_cost(self.vehicle)
        self.other_cost = self.make_cost(self.other_vehicle)
        self.client.force_login(self.users['staff'])
        self.url = reverse('vehicle_invoices', args=[self.vehicle.pk])

    def make_cost(self, vehicle):
        return VehicleCostEntry.objects.create(vehicle=vehicle, kind='cost', category='repair', description='Synthetic repair', amount_cents=10000, effective_on=timezone.localdate(), actor=self.users['staff'])

    def upload(self, *, cost='', data=PDF, key=None):
        return self.client.post(self.url, {'title': 'Synthetic invoice', 'cost': cost, 'upload_key': key or uuid.uuid4(), 'pdf_file': SimpleUploadedFile('invoice.pdf', data, content_type='application/pdf')})

    def test_upload_download_preserve_bytes_and_audit(self):
        self.assertEqual(self.upload(cost=self.cost.pk).status_code, 302)
        invoice = VehicleInvoice.objects.get()
        self.assertEqual(invoice.cost, self.cost)
        url = reverse('vehicle_invoice_download', args=[self.vehicle.pk, invoice.pk])
        response = self.client.get(url)
        self.assertEqual(response.content, PDF)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(list(invoice.events.order_by('pk').values_list('action', flat=True)), ['upload', 'download'])
        self.assertEqual(self.client.head(url).status_code, 200)
        self.assertEqual(invoice.events.count(), 2)

    def test_upload_service_denies_inactive_and_disabled_even_for_retry(self):
        from django.core.exceptions import PermissionDenied
        from .invoice_views import upload_invoice
        args = dict(vehicle_id=self.vehicle.pk, dealership_id=self.dealer.pk, actor=self.users['staff'],
                    title='Synthetic invoice', upload_key=uuid.uuid4(), pdf_bytes=PDF, cost_id=None)
        invoice = upload_invoice(**args)
        self.users['staff'].is_active = False
        self.users['staff'].save(update_fields=['is_active'])
        with self.assertRaises(PermissionDenied):
            upload_invoice(**args)
        self.users['staff'].is_active = True
        self.users['staff'].save(update_fields=['is_active'])
        with override_settings(RECON_DEMO_ENABLED=False), self.assertRaises(PermissionDenied):
            upload_invoice(**args)
        self.assertEqual(VehicleInvoice.objects.count(), 1)
        self.assertEqual(VehicleInvoiceEvent.objects.filter(invoice=invoice).count(), 1)

    def test_unlinked_duplicate_and_invalid_files(self):
        self.assertEqual(self.upload(data=b'not a pdf').status_code, 200)
        self.assertEqual(VehicleInvoice.objects.count(), 0)
        key = uuid.uuid4()
        self.assertEqual(self.upload(key=key).status_code, 302)
        self.assertEqual(self.upload(key=key).status_code, 302)
        self.assertEqual(VehicleInvoice.objects.count(), 1)
        self.assertEqual(self.upload(key=key, data=PDF + b'changed').status_code, 200)
        self.assertEqual(VehicleInvoice.objects.count(), 1)

    def test_same_vehicle_cost_is_enforced_and_viewer_cannot_upload(self):
        self.assertEqual(self.upload(cost=self.other_cost.pk).status_code, 200)
        self.assertFalse(VehicleInvoice.objects.exists())
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_cross_dealer_and_integrity_fail_closed(self):
        self.upload()
        invoice = VehicleInvoice.objects.get()
        url = reverse('vehicle_invoice_download', args=[self.vehicle.pk, invoice.pk])
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.users['staff'])
        with invoice.blob.open('wb') as target:
            target.write(b'tampered')
        self.assertEqual(self.client.get(url).status_code, 409)
        self.assertEqual(VehicleInvoiceEvent.objects.count(), 1)

    def test_download_role_and_cache_matrix(self):
        self.upload()
        invoice = VehicleInvoice.objects.get()
        url = reverse('vehicle_invoice_download', args=[self.vehicle.pk, invoice.pk])
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

    def test_shared_storage_alias_is_denied(self):
        self.upload()
        invoice = VehicleInvoice.objects.get()
        foreign_vehicle = Vehicle.objects.create(dealership=self.other, stock_number='FOREIGN-I', year=2020, make='Demo', model='Car')
        VehicleInvoice.objects.create(vehicle=foreign_vehicle, title='Foreign', blob=invoice.blob.name.replace('vehicle-invoices/', 'vehicle-invoices/./'), sha256=invoice.sha256, byte_size=invoice.byte_size, created_by=self.users['foreign'])
        url = reverse('vehicle_invoice_download', args=[self.vehicle.pk, invoice.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertFalse(invoice.events.filter(action='download').exists())

    def test_failed_download_audit_returns_no_file(self):
        self.upload()
        invoice = VehicleInvoice.objects.get()
        url = reverse('vehicle_invoice_download', args=[self.vehicle.pk, invoice.pk])
        with patch('documents.invoice_views.VehicleInvoiceEvent.objects.create', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.client.get(url)
        self.assertFalse(invoice.events.filter(action='download').exists())

    @override_settings(RECON_DEMO_ENABLED=False)
    def test_disabled_gate(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.upload().status_code, 404)

    def test_reversal_keeps_original_invoice_association_and_bytes(self):
        self.upload(cost=self.cost.pk)
        invoice = VehicleInvoice.objects.get()
        VehicleCostEntry.objects.create(vehicle=self.vehicle, kind='reversal', category='repair', description=self.cost.description, amount_cents=self.cost.amount_cents, debit='cost_offset', credit='vehicle_cost', reverses=self.cost, reason='Correction', effective_on=timezone.localdate(), actor=self.users['staff'])
        invoice.refresh_from_db()
        self.assertEqual(invoice.cost_id, self.cost.pk)
        self.assertEqual(self.client.get(reverse('vehicle_invoice_download', args=[self.vehicle.pk, invoice.pk])).content, PDF)

    def test_size_limit_and_pdf_trailer(self):
        from .services import MAX_FILE_BYTES
        self.assertEqual(self.upload(data=b'%PDF-1.7\nmissing trailer').status_code, 200)
        self.assertEqual(self.upload(data=b'%PDF-' + b'x' * MAX_FILE_BYTES + b'%%EOF').status_code, 200)
        self.assertFalse(VehicleInvoice.objects.exists())

    def test_service_rejects_cross_vehicle_cost_and_unauthorized_actor(self):
        from django.core.exceptions import PermissionDenied
        from .invoice_views import upload_invoice
        from .services import FileWorkflowError
        args = dict(vehicle_id=self.vehicle.pk, dealership_id=self.dealer.pk, title='Synthetic', upload_key=uuid.uuid4(), pdf_bytes=PDF)
        with self.assertRaises(FileWorkflowError):
            upload_invoice(actor=self.users['staff'], cost_id=self.other_cost.pk, **args)
        with self.assertRaises(PermissionDenied):
            upload_invoice(actor=self.users['viewer'], cost_id=None, **args)
        self.assertFalse(VehicleInvoice.objects.exists())

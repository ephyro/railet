# SPDX-License-Identifier: MPL-2.0
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from core.models import Dealership
from inventory.models import Vehicle
from .models import VehicleInvoice, VehicleInvoiceEvent


def seed():
    dealer = Dealership.objects.create(name='Synthetic invoice audit dealer')
    actor = get_user_model().objects.create_user('synthetic-invoice-auditor')
    vehicle = Vehicle.objects.create(dealership=dealer, stock_number='SYN-INVOICE', year=2020,
        make='Synthetic', model='Car')
    invoice = VehicleInvoice.objects.create(vehicle=vehicle, title='Invented invoice',
        blob='vehicle-invoices/synthetic.pdf', sha256='0' * 64, byte_size=1, created_by=actor)
    return invoice, actor, VehicleInvoiceEvent.objects.create(invoice=invoice, actor=actor, action='upload')


def assert_guards(case, event):
    original = VehicleInvoiceEvent.objects.filter(pk=event.pk).values().get()
    for sql in ("UPDATE documents_vehicleinvoiceevent SET action = 'download' WHERE id = %s",
                'DELETE FROM documents_vehicleinvoiceevent WHERE id = %s'):
        with case.assertRaisesMessage(DatabaseError, 'Invoice events are immutable'):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, [event.pk])
        case.assertEqual(VehicleInvoiceEvent.objects.filter(pk=event.pk).values().get(), original)


class InvoiceEventGuardTests(TestCase):
    def test_append_allowed_mutation_rejected_and_fields_preserved(self):
        invoice, actor, event = seed()
        assert_guards(self, event)
        next_event = VehicleInvoiceEvent.objects.create(invoice=invoice, actor=actor, action='download')
        assert_guards(self, next_event)
        self.assertEqual(invoice.events.count(), 2)


class InvoiceEventMigrationTests(TransactionTestCase):
    def test_existing_history_preserved_and_reverse_reapply(self):
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            MigrationExecutor(connection).migrate([('documents', '0005_vehicleacquisitionfile_vehicleacquisitionfileevent_and_more')])
            _, _, event = seed()
            baseline = VehicleInvoiceEvent.objects.values().get(pk=event.pk)
            MigrationExecutor(connection).migrate([('documents', '0006_invoice_event_immutable')])
            self.assertEqual(VehicleInvoiceEvent.objects.values().get(pk=event.pk), baseline)
            assert_guards(self, event)
            MigrationExecutor(connection).migrate([('documents', '0005_vehicleacquisitionfile_vehicleacquisitionfileevent_and_more')])
            VehicleInvoiceEvent.objects.filter(pk=event.pk).update(action='download')
            VehicleInvoiceEvent.objects.filter(pk=event.pk).delete()
            self.assertFalse(VehicleInvoiceEvent.objects.filter(pk=event.pk).exists())
            MigrationExecutor(connection).migrate([('documents', '0006_invoice_event_immutable')])
            _, _, new_event = self.append_event()
            assert_guards(self, new_event)
        finally:
            # SQLite's test flush uses DELETE, so remove this test's events only
            # while the reversible guard is absent, then restore the schema.
            MigrationExecutor(connection).migrate([('documents', '0005_vehicleacquisitionfile_vehicleacquisitionfileevent_and_more')])
            VehicleInvoiceEvent.objects.all().delete()
            MigrationExecutor(connection).migrate(latest)

    def append_event(self):
        invoice = VehicleInvoice.objects.get()
        actor = get_user_model().objects.get(username='synthetic-invoice-auditor')
        return invoice, actor, VehicleInvoiceEvent.objects.create(invoice=invoice, actor=actor, action='download')

# SPDX-License-Identifier: MPL-2.0
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from core.models import Dealership
from inventory.models import Vehicle
from customers.models import Customer
from deals.models import DraftDeal
from django.utils import timezone
from .models import DemoDealPacket, DemoPacketExportEvent


def seed():
    dealer = Dealership.objects.create(name='Synthetic packet audit dealer')
    actor = get_user_model().objects.create_user('synthetic-packet-auditor')
    vehicle = Vehicle.objects.create(dealership=dealer, stock_number='SYN-PACKET', year=2020,
        make='Synthetic', model='Car')
    buyer = Customer.objects.create(dealership=dealer, first_name='Synthetic', last_name='Buyer')
    deal = DraftDeal.objects.create(dealership=dealer, vehicle=vehicle, buyer=buyer)
    packet = DemoDealPacket.objects.create(deal=deal, created_by=actor, created_at=timezone.now(),
        template_version='synthetic-test', snapshot={}, source_sha256='0' * 64,
        html='Synthetic test artifact', artifact_sha256='0' * 64)
    return packet, actor, DemoPacketExportEvent.objects.create(packet=packet, actor=actor, bundle_sha256='1' * 64)


def assert_guards(case, event):
    original = DemoPacketExportEvent.objects.filter(pk=event.pk).values().get()
    for sql in ("UPDATE documents_demopacketexportevent SET bundle_sha256 = 'changed' WHERE id = %s",
                'DELETE FROM documents_demopacketexportevent WHERE id = %s'):
        with case.assertRaisesMessage(DatabaseError, 'Packet export events are immutable'):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, [event.pk])
        case.assertEqual(DemoPacketExportEvent.objects.filter(pk=event.pk).values().get(), original)


class PacketExportEventGuardTests(TestCase):
    def test_append_allowed_mutation_rejected_and_fields_preserved(self):
        packet, actor, event = seed()
        assert_guards(self, event)
        next_event = DemoPacketExportEvent.objects.create(packet=packet, actor=actor, bundle_sha256='2' * 64)
        assert_guards(self, next_event)
        self.assertEqual(packet.export_events.count(), 2)


class PacketExportEventMigrationTests(TransactionTestCase):
    def test_existing_history_preserved_and_reverse_reapply(self):
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            MigrationExecutor(connection).migrate([('documents', '0006_invoice_event_immutable')])
            _, _, event = seed()
            baseline = DemoPacketExportEvent.objects.values().get(pk=event.pk)
            MigrationExecutor(connection).migrate([('documents', '0007_packet_export_event_immutable')])
            self.assertEqual(DemoPacketExportEvent.objects.values().get(pk=event.pk), baseline)
            assert_guards(self, event)
            MigrationExecutor(connection).migrate([('documents', '0006_invoice_event_immutable')])
            DemoPacketExportEvent.objects.filter(pk=event.pk).update(bundle_sha256='3' * 64)
            DemoPacketExportEvent.objects.filter(pk=event.pk).delete()
            self.assertFalse(DemoPacketExportEvent.objects.filter(pk=event.pk).exists())
            MigrationExecutor(connection).migrate([('documents', '0007_packet_export_event_immutable')])
            _, _, new_event = self.append_event()
            assert_guards(self, new_event)
        finally:
            # SQLite's test flush uses DELETE, so remove this test's events only
            # while the reversible guard is absent, then restore the schema.
            MigrationExecutor(connection).migrate([('documents', '0006_invoice_event_immutable')])
            DemoPacketExportEvent.objects.all().delete()
            MigrationExecutor(connection).migrate(latest)

    def append_event(self):
        packet = DemoDealPacket.objects.get()
        actor = get_user_model().objects.get(username='synthetic-packet-auditor')
        return packet, actor, DemoPacketExportEvent.objects.create(packet=packet, actor=actor, bundle_sha256='2' * 64)

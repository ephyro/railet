# SPDX-License-Identifier: MPL-2.0
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from core.models import Dealership, Membership
from inventory.models import Vehicle
from customers.models import Customer
from deals.models import DraftDeal
from .models import DealFile, DealFileEvent


def seed():
    dealer = Dealership.objects.create(name='Synthetic packet audit dealer')
    actor = get_user_model().objects.create_user('synthetic-packet-auditor')
    Membership.objects.create(user=actor, dealership=dealer, role='staff')
    vehicle = Vehicle.objects.create(dealership=dealer, stock_number='SYN-PACKET', year=2020,
        make='Synthetic', model='Car')
    buyer = Customer.objects.create(dealership=dealer, first_name='Synthetic', last_name='Buyer')
    deal = DraftDeal.objects.create(dealership=dealer, vehicle=vehicle, buyer=buyer)
    packet = DealFile.objects.create(deal=deal, created_by=actor, title='Synthetic supporting file',
        blob='deal-files/synthetic.pdf', sha256='0' * 64, byte_size=1)
    return packet, actor, DealFileEvent.objects.create(file=packet, actor=actor, action='upload')


def assert_guards(case, event):
    original = DealFileEvent.objects.filter(pk=event.pk).values().get()
    for sql in ("UPDATE documents_dealfileevent SET reason = 'changed' WHERE id = %s",
                'DELETE FROM documents_dealfileevent WHERE id = %s'):
        with case.assertRaisesMessage(DatabaseError, 'Deal file events are immutable'):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, [event.pk])
        case.assertEqual(DealFileEvent.objects.filter(pk=event.pk).values().get(), original)


@override_settings(DEAL_FILES_DEMO_ENABLED=True)
class DealFileEventGuardTests(TestCase):
    def test_append_allowed_mutation_rejected_and_fields_preserved(self):
        packet, actor, event = seed()
        assert_guards(self, event)
        next_event = DealFileEvent.objects.create(file=packet, actor=actor, action='download')
        assert_guards(self, next_event)
        self.assertEqual(packet.events.count(), 2)
        from .services import change_deal_file_state
        for action in ('archive', 'restore'):
            change_deal_file_state(deal_id=packet.deal_id, file_id=packet.pk,
                dealership_id=packet.deal.dealership_id, actor=actor, action=action,
                reason='Synthetic archive rehearsal')
        self.assertEqual(packet.events.count(), 4)
        assert_guards(self, event)



class DealFileEventMigrationTests(TransactionTestCase):
    def test_existing_history_preserved_and_reverse_reapply(self):
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            MigrationExecutor(connection).migrate([('documents', '0007_packet_export_event_immutable')])
            _, _, event = seed()
            baseline = DealFileEvent.objects.values().get(pk=event.pk)
            MigrationExecutor(connection).migrate([('documents', '0008_deal_file_event_immutable')])
            self.assertEqual(DealFileEvent.objects.values().get(pk=event.pk), baseline)
            assert_guards(self, event)
            MigrationExecutor(connection).migrate([('documents', '0007_packet_export_event_immutable')])
            DealFileEvent.objects.filter(pk=event.pk).update(reason='changed')
            DealFileEvent.objects.filter(pk=event.pk).delete()
            self.assertFalse(DealFileEvent.objects.filter(pk=event.pk).exists())
            MigrationExecutor(connection).migrate([('documents', '0008_deal_file_event_immutable')])
            _, _, new_event = self.append_event()
            assert_guards(self, new_event)
        finally:
            # SQLite's test flush uses DELETE, so remove this test's events only
            # while the reversible guard is absent, then restore the schema.
            MigrationExecutor(connection).migrate([('documents', '0007_packet_export_event_immutable')])
            DealFileEvent.objects.all().delete()
            MigrationExecutor(connection).migrate(latest)

    def append_event(self):
        packet = DealFile.objects.get()
        actor = get_user_model().objects.get(username='synthetic-packet-auditor')
        return packet, actor, DealFileEvent.objects.create(file=packet, actor=actor, action='download')

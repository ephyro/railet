# SPDX-License-Identifier: MPL-2.0
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from core.models import Dealership
from .models import VehicleVendor, VehicleVendorEvent


def seed():
    dealer = Dealership.objects.create(name='Synthetic vendor audit dealer')
    actor = get_user_model().objects.create_user('synthetic-vendor-auditor')
    vendor = VehicleVendor.objects.create(dealership=dealer, name='Synthetic garage',
        normalized_name='synthetic garage', created_by=actor)
    return vendor, actor, VehicleVendorEvent.objects.create(vendor=vendor, actor=actor,
        action='created', changes={'name': 'Synthetic garage'})


def assert_guards(case, event):
    original = VehicleVendorEvent.objects.filter(pk=event.pk).values().get()
    for sql in ("UPDATE inventory_vehiclevendorevent SET changes = '{}' WHERE id = %s",
                'DELETE FROM inventory_vehiclevendorevent WHERE id = %s'):
        with case.assertRaisesMessage(DatabaseError, 'Vendor events are immutable'):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, [event.pk])
        case.assertEqual(VehicleVendorEvent.objects.filter(pk=event.pk).values().get(), original)


class VendorEventGuardTests(TestCase):
    def test_append_allowed_mutation_rejected_and_fields_preserved(self):
        vendor, actor, event = seed()
        assert_guards(self, event)
        next_event = VehicleVendorEvent.objects.create(vendor=vendor, actor=actor,
            action='updated', changes={'before': 'Synthetic garage', 'after': 'Synthetic workshop'})
        assert_guards(self, next_event)
        self.assertEqual(vendor.events.count(), 2)


class VendorEventMigrationTests(TransactionTestCase):
    def test_existing_history_preserved_and_reverse_reapply(self):
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            MigrationExecutor(connection).migrate([('inventory', '0011_vehicle_sold_on')])
            _, _, event = seed()
            baseline = VehicleVendorEvent.objects.values().get(pk=event.pk)
            MigrationExecutor(connection).migrate([('inventory', '0012_vendor_event_immutable')])
            self.assertEqual(VehicleVendorEvent.objects.values().get(pk=event.pk), baseline)
            assert_guards(self, event)
            MigrationExecutor(connection).migrate([('inventory', '0011_vehicle_sold_on')])
            VehicleVendorEvent.objects.filter(pk=event.pk).update(action='updated')
            VehicleVendorEvent.objects.filter(pk=event.pk).delete()
            self.assertFalse(VehicleVendorEvent.objects.filter(pk=event.pk).exists())
            MigrationExecutor(connection).migrate([('inventory', '0012_vendor_event_immutable')])
            _, _, new_event = self.append_event()
            assert_guards(self, new_event)
        finally:
            # SQLite's test flush uses DELETE, so remove this test's events only
            # while the reversible guard is absent, then restore the schema.
            MigrationExecutor(connection).migrate([('inventory', '0011_vehicle_sold_on')])
            VehicleVendorEvent.objects.all().delete()
            MigrationExecutor(connection).migrate(latest)

    def append_event(self):
        vendor = VehicleVendor.objects.get()
        actor = get_user_model().objects.get(username='synthetic-vendor-auditor')
        return vendor, actor, VehicleVendorEvent.objects.create(vendor=vendor, actor=actor,
            action='updated', changes={'synthetic': True})

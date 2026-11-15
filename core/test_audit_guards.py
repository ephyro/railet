# SPDX-License-Identifier: MPL-2.0
"""Database guards and test-only legacy-corruption fixture support."""
from importlib import import_module

from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.test import TestCase

from core.models import AuditEvent, Dealership, Membership
from inventory.models import Vehicle


def legacy_mismatch_fixture(**kwargs):
    """Simulate a pre-migration row only inside an isolated test database."""
    database = str(connection.settings_dict['NAME'])
    if not connection.in_atomic_block or not (
        database.startswith('test_') or database.startswith('file:memorydb_') or database == ':memory:'
    ):
        raise RuntimeError('Legacy fixture requires an isolated transactional test database.')
    guards = import_module('core.migrations.0008_inventory_audit_guards')
    with connection.cursor() as cursor:
        guards.drop_insert(cursor, connection.vendor)
        try:
            event = AuditEvent.objects.create(**kwargs)
        finally:
            guards.install_insert(cursor, connection.vendor)
    return event


class InventoryAuditGuardTests(TestCase):
    def setUp(self):
        self.dealer = Dealership.objects.create(name='Synthetic audit dealer')
        self.other = Dealership.objects.create(name='Other synthetic dealer')
        self.actor = get_user_model().objects.create_user('synthetic-audit-guard')
        Membership.objects.create(user=self.actor, dealership=self.dealer, role='staff')
        self.vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='AUDIT-1', year=2020, make='Synthetic', model='Car')
        self.other_vehicle = Vehicle.objects.create(dealership=self.other, stock_number='AUDIT-2', year=2020, make='Synthetic', model='Other')

    def test_valid_insert_mismatch_and_mutation_guards(self):
        event = AuditEvent.objects.create(dealership=self.dealer, vehicle=self.vehicle, actor=self.actor,
                                          action='created', changes={'synthetic': True})
        for vehicle, dealer in ((self.other_vehicle, self.dealer), (self.vehicle, self.other)):
            with self.subTest(vehicle=vehicle.pk), self.assertRaises(DatabaseError), transaction.atomic():
                AuditEvent.objects.create(dealership=dealer, vehicle=vehicle, actor=self.actor,
                                          action='invalid', changes={})
        for operation in ('update', 'delete'):
            with self.subTest(operation=operation), self.assertRaises(DatabaseError), transaction.atomic():
                qs = AuditEvent.objects.filter(pk=event.pk)
                qs.update(action='changed') if operation == 'update' else qs.delete()
        event.refresh_from_db()
        self.assertEqual((event.action, event.changes), ('created', {'synthetic': True}))

    def test_vehicle_ownership_cannot_change_after_audit(self):
        AuditEvent.objects.create(dealership=self.dealer, vehicle=self.vehicle, actor=self.actor,
                                  action='created', changes={})
        with self.assertRaises(DatabaseError), transaction.atomic():
            Vehicle.objects.filter(pk=self.vehicle.pk).update(dealership=self.other)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.dealership_id, self.dealer.pk)
        Vehicle.objects.filter(pk=self.other_vehicle.pk).update(dealership=self.dealer)
        self.other_vehicle.refresh_from_db()
        self.assertEqual(self.other_vehicle.dealership_id, self.dealer.pk)

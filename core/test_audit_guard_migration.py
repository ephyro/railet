# SPDX-License-Identifier: MPL-2.0
"""Round-trip audit guards and serialize ownership changes in test databases."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from core.models import AuditEvent, Dealership, Membership
from inventory.models import Vehicle


class AuditMigrationFixture(TransactionTestCase):
    def setUp(self):
        self.dealer = Dealership.objects.create(name='Synthetic migration dealer')
        self.other = Dealership.objects.create(name='Other synthetic migration dealer')
        self.actor = get_user_model().objects.create_user('synthetic-audit-migration')
        Membership.objects.create(user=self.actor, dealership=self.dealer, role='owner')
        self.vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='AUDIT-MIGRATION',
                                              year=2020, make='Synthetic', model='Car')

    def migrate(self, target):
        MigrationExecutor(connection).migrate([('core', target)])

    def latest(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def tearDown(self):
        # SQLite's test flush issues DELETE; remove only these isolated test rows
        # after reversing the guards, then restore the schema before test teardown.
        try:
            self.migrate('0007_synthetic_mfa_event_immutable')
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM core_auditevent WHERE vehicle_id = %s', [self.vehicle.pk])
        finally:
            self.latest()
        super().tearDown()


class InventoryAuditMigrationTests(AuditMigrationFixture):
    def test_legacy_rows_survive_forward_reverse_forward_and_remain_guarded(self):
        self.migrate('0007_synthetic_mfa_event_immutable')
        event = AuditEvent.objects.create(dealership=self.other, vehicle=self.vehicle, actor=self.actor,
            action='legacy synthetic', changes={'legacy': 'preserved'})
        before = AuditEvent.objects.filter(pk=event.pk).values().get()
        self.latest()
        self.assertEqual(AuditEvent.objects.filter(pk=event.pk).values().get(), before)
        for action in ('insert', 'update', 'delete'):
            with self.subTest(action=action), self.assertRaises(DatabaseError), transaction.atomic():
                if action == 'insert':
                    AuditEvent.objects.create(dealership=self.other, vehicle=self.vehicle, actor=self.actor,
                                              action='new mismatch', changes={})
                elif action == 'update':
                    AuditEvent.objects.filter(pk=event.pk).update(action='changed')
                else:
                    AuditEvent.objects.filter(pk=event.pk).delete()
        self.migrate('0007_synthetic_mfa_event_immutable')
        self.assertEqual(AuditEvent.objects.filter(pk=event.pk).values().get(), before)
        self.latest()
        self.assertEqual(AuditEvent.objects.filter(pk=event.pk).values().get(), before)
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuditEvent.objects.filter(pk=event.pk).update(action='changed')


@skipUnless(connection.vendor == 'postgresql', 'Vehicle row-lock race requires PostgreSQL')
class InventoryAuditRaceTests(AuditMigrationFixture):
    def test_audit_insert_serializes_with_vehicle_dealership_change(self):
        inserted, release, attempting = Event(), Event(), Event()

        def insert_audit():
            close_old_connections()
            try:
                with transaction.atomic():
                    AuditEvent.objects.create(dealership_id=self.dealer.pk, vehicle_id=self.vehicle.pk,
                        actor_id=self.actor.pk, action='created', changes={'synthetic': True})
                    inserted.set()
                    if not release.wait(10):
                        raise RuntimeError('Synthetic race timed out')
            finally:
                close_old_connections()

        def move_vehicle():
            close_old_connections()
            try:
                if not inserted.wait(10):
                    raise RuntimeError('Synthetic race did not start')
                attempting.set()
                try:
                    with transaction.atomic():
                        Vehicle.objects.filter(pk=self.vehicle.pk).update(dealership_id=self.other.pk)
                except DatabaseError:
                    return 'rejected'
                return 'moved'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(insert_audit)
            second = pool.submit(move_vehicle)
            try:
                self.assertTrue(attempting.wait(10))
                with self.assertRaises(TimeoutError):
                    second.result(timeout=0.3)
            finally:
                release.set()
            first.result(timeout=10)
            self.assertEqual(second.result(timeout=10), 'rejected')
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.dealership_id, self.dealer.pk)
        self.assertEqual(AuditEvent.objects.filter(vehicle=self.vehicle).count(), 1)

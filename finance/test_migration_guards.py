# SPDX-License-Identifier: MPL-2.0
"""Round-trip historic finance migrations on the isolated Django test database."""
from datetime import date
from importlib import import_module
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from core.models import Dealership, Membership
from customers.models import Customer
from deals.models import DraftDeal
from inventory.models import Vehicle
from .models import DemoAccountContext, DemoAccountExport, DemoBook


class FinanceGuardMigrationTests(TransactionTestCase):
    def setUp(self):
        self.dealer = Dealership.objects.create(name='Synthetic migration guard dealer')
        self.user = get_user_model().objects.create_user('synthetic-guard-owner')
        Membership.objects.create(user=self.user, dealership=self.dealer, role='owner')
        customer = Customer.objects.create(dealership=self.dealer, first_name='Synthetic')
        vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='GUARD-MIGRATE', year=2020, make='Synthetic', model='Car')
        deal = DraftDeal.objects.create(dealership=self.dealer, buyer=customer, vehicle=vehicle, deal_type='bhph')
        self.book = DemoBook.objects.create(dealership=self.dealer, customer=customer, label='Synthetic',
            source_reference='Synthetic', opening_on=date(2026, 1, 1), created_by=self.user, creation_key=uuid4())
        self.context = DemoAccountContext.objects.create(book=self.book, deal=deal, created_by=self.user,
            snapshot={'synthetic': 'original'}, snapshot_sha256='a' * 64)

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate([('finance', target)])

    def latest(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def assert_immutable(self, table, record_id, column):
        for statement in (f'UPDATE {table} SET {column} = {column} WHERE id = %s',
                          f'DELETE FROM {table} WHERE id = %s'):
            with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(statement, [record_id])

    def test_export_record_and_guards_survive_each_rebuild_in_both_directions(self):
        event = DemoAccountExport.objects.create(book=self.book, actor=self.user, bundle_sha256='b' * 64,
            bundle_bytes=123, posting_count=0, schedule_count=0)
        for target in ('0013_payment_method', '0012_servicing_guards_export_version',
                       '0011_demo_servicing_plan', '0010_alter_demoaccountexport_format_version',
                       '0009_export_audit_immutable', '0010_alter_demoaccountexport_format_version',
                       '0012_servicing_guards_export_version', '0013_payment_method',
                       '0015_restore_export_audit_guards'):
            with self.subTest(target=target):
                self.migrate(target)
                with connection.cursor() as cursor:
                    cursor.execute('SELECT book_id, actor_id, bundle_sha256, bundle_bytes FROM finance_demoaccountexport WHERE id = %s', [event.pk])
                    self.assertEqual(cursor.fetchone(), (self.book.pk, self.user.pk, 'b' * 64, 123))
                self.assert_immutable('finance_demoaccountexport', event.pk, 'bundle_sha256')
        self.latest()
        self.assert_immutable('finance_demoaccountexport', event.pk, 'bundle_sha256')

    def test_context_record_and_guards_survive_constraint_rebuilds(self):
        for target in ('0007_demoaccountcontext_one_demo_account_per_draft',
                       '0006_account_context_immutable',
                       '0007_demoaccountcontext_one_demo_account_per_draft',
                       '0015_restore_export_audit_guards'):
            with self.subTest(target=target):
                self.migrate(target)
                with connection.cursor() as cursor:
                    cursor.execute('SELECT book_id, deal_id, snapshot_sha256 FROM finance_demoaccountcontext WHERE id = %s', [self.context.pk])
                    self.assertEqual(cursor.fetchone(), (self.book.pk, self.context.deal_id, 'a' * 64))
                self.assert_immutable('finance_demoaccountcontext', self.context.pk, 'snapshot_sha256')
        self.latest()

    def test_legacy_sqlite_reversal_tolerates_already_missing_guards(self):
        if connection.vendor != 'sqlite':
            self.skipTest('SQLite table rebuild behavior')
        # This reproduces the pre-repair state in the isolated test database.
        with connection.schema_editor() as editor:
            for name in ('demo_account_export_update', 'demo_account_export_delete',
                         'demo_account_context_update', 'demo_account_context_delete'):
                editor.execute(f'DROP TRIGGER IF EXISTS {name}')
            import_module('finance.migrations.0009_export_audit_immutable').backwards(None, editor)
            import_module('finance.migrations.0006_account_context_immutable').backwards(None, editor)
            import_module('finance.migrations.0009_export_audit_immutable').restore_sqlite_guards(None, editor)
            import_module('finance.migrations.0006_account_context_immutable').restore_sqlite_guards(None, editor)
        self.assert_immutable('finance_demoaccountcontext', self.context.pk, 'snapshot_sha256')

    def tearDown(self):
        try:
            # Tear down only the isolated test fixture; reverting below model
            # creation drops its test tables, and 0002 removes book guards.
            self.migrate('0001_initial')
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM finance_demobook WHERE id = %s', [self.book.pk])
        finally:
            self.latest()
        super().tearDown()

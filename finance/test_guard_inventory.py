# SPDX-License-Identifier: MPL-2.0
"""Verify the finance guards installed by the full migration graph."""
from django.db import connection
from django.test import TestCase


class FinanceTriggerInventoryTests(TestCase):
    def test_migrated_finance_guards_exist_on_the_expected_tables_and_events(self):
        # These are the backend-specific guards installed by finance migrations.
        # SQLite intentionally has fewer cross-record INSERT guards than PostgreSQL.
        sqlite = {
            'demo_book_update': ('finance_demobook', ('UPDATE',)),
            'demo_book_delete': ('finance_demobook', ('DELETE',)),
            'demo_posting_update': ('finance_demoposting', ('UPDATE',)),
            'demo_posting_delete': ('finance_demoposting', ('DELETE',)),
            'demo_schedule_update': ('finance_demoschedule', ('UPDATE',)),
            'demo_schedule_delete': ('finance_demoschedule', ('DELETE',)),
            'demo_account_context_update': ('finance_demoaccountcontext', ('UPDATE',)),
            'demo_account_context_delete': ('finance_demoaccountcontext', ('DELETE',)),
            'demo_account_context_check': ('finance_demoaccountcontext', ('INSERT',)),
            'demo_account_export_update': ('finance_demoaccountexport', ('UPDATE',)),
            'demo_account_export_delete': ('finance_demoaccountexport', ('DELETE',)),
            'demo_servicing_update': ('finance_demoservicingplan', ('UPDATE',)),
            'demo_servicing_delete': ('finance_demoservicingplan', ('DELETE',)),
            'demo_servicing_check': ('finance_demoservicingplan', ('INSERT',)),
            'demo_payment_method_check': ('finance_demoposting', ('INSERT',)),
        }
        postgres = {
            'demo_book_immutable': ('finance_demobook', ('UPDATE', 'DELETE')),
            'demo_book_check': ('finance_demobook', ('INSERT',)),
            'demo_posting_immutable': ('finance_demoposting', ('UPDATE', 'DELETE')),
            'demo_posting_check': ('finance_demoposting', ('INSERT',)),
            'demo_schedule_immutable': ('finance_demoschedule', ('UPDATE', 'DELETE')),
            'demo_schedule_check': ('finance_demoschedule', ('INSERT',)),
            'demo_account_context_immutable': ('finance_demoaccountcontext', ('UPDATE', 'DELETE')),
            'demo_account_context_check': ('finance_demoaccountcontext', ('INSERT',)),
            'demo_account_export_immutable': ('finance_demoaccountexport', ('UPDATE', 'DELETE')),
            'demo_account_export_check': ('finance_demoaccountexport', ('INSERT',)),
            'demo_servicing_immutable': ('finance_demoservicingplan', ('UPDATE', 'DELETE')),
            'demo_servicing_check': ('finance_demoservicingplan', ('INSERT',)),
            'demo_payment_method_check': ('finance_demoposting', ('INSERT',)),
        }
        with connection.cursor() as cursor:
            if connection.vendor == 'sqlite':
                cursor.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger'")
                actual = {name: (table, sql, True) for name, table, sql in cursor.fetchall()}
                expected = sqlite
            elif connection.vendor == 'postgresql':
                cursor.execute("""SELECT t.tgname, c.relname, pg_get_triggerdef(t.oid), t.tgenabled
                    FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                    JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE NOT t.tgisinternal AND n.nspname=current_schema()""")
                actual = {name: (table, sql, enabled in ('O', 'A')) for name, table, sql, enabled in cursor.fetchall()}
                expected = postgres
            else:
                self.skipTest('Finance trigger migrations support SQLite and PostgreSQL')
        for name, (table, operations) in expected.items():
            with self.subTest(trigger=name):
                self.assertIn(name, actual)
                actual_table, sql, enabled = actual[name]
                self.assertEqual(actual_table, table)
                self.assertTrue(enabled)
                self.assertIn('BEFORE', sql.upper())
                for operation in operations:
                    self.assertIn(operation, sql.upper())

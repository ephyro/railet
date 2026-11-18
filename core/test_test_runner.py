# SPDX-License-Identifier: MPL-2.0
from unittest.mock import Mock
from unittest import skipUnless
from django.db import DatabaseError, connection, transaction
from django.test import TestCase
from .test_runner import guarded_flush


@skipUnless(connection.vendor == 'sqlite', 'SQLite test flush adapter')
class GuardedFlushTests(TestCase):
    def test_refuses_unregistered_database(self):
        callback = Mock()
        with self.assertRaises(RuntimeError):
            guarded_flush(connection, 'not-this-database', callback, [])
        disk = Mock(vendor='sqlite', settings_dict={'NAME': '/tmp/existing.sqlite3'})
        with self.assertRaises(RuntimeError):
            guarded_flush(disk, '/tmp/existing.sqlite3', callback, [])
        callback.assert_not_called()

    def test_cleanup_restores_exact_trigger_and_preserves_update_guard(self):
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE synthetic_flush_probe (id integer primary key, value integer)')
            cursor.execute('INSERT INTO synthetic_flush_probe VALUES (1, 10)')
            cursor.execute("CREATE TRIGGER synthetic_probe_delete BEFORE DELETE ON synthetic_flush_probe BEGIN SELECT RAISE(ABORT, 'synthetic delete guard'); END")
            cursor.execute("CREATE TRIGGER synthetic_probe_update BEFORE UPDATE ON synthetic_flush_probe BEGIN SELECT RAISE(ABORT, 'synthetic update guard'); END")
            cursor.execute("SELECT name, sql FROM sqlite_master WHERE name LIKE 'synthetic_probe_%' ORDER BY name")
            before = cursor.fetchall()
        def flush(sql):
            with self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('UPDATE synthetic_flush_probe SET value = 20')
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM synthetic_flush_probe')
        guarded_flush(connection, str(connection.settings_dict['NAME']), flush, [])
        with connection.cursor() as cursor:
            cursor.execute("SELECT name, sql FROM sqlite_master WHERE name LIKE 'synthetic_probe_%' ORDER BY name")
            self.assertEqual(cursor.fetchall(), before)
            cursor.execute('INSERT INTO synthetic_flush_probe VALUES (2, 10)')
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM synthetic_flush_probe')
        with self.assertRaisesRegex(ValueError, 'synthetic failure'):
            guarded_flush(connection, str(connection.settings_dict['NAME']),
                          Mock(side_effect=ValueError('synthetic failure')), [])
        with connection.cursor() as cursor:
            cursor.execute("SELECT name, sql FROM sqlite_master WHERE name LIKE 'synthetic_probe_%' ORDER BY name")
            self.assertEqual(cursor.fetchall(), before)

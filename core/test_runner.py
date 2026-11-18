# SPDX-License-Identifier: MPL-2.0
"""SQLite test-flush isolation; production guards remain active during tests."""
import re
from types import MethodType

from django.db import connections, transaction
from django.test.runner import DiscoverRunner

_DELETE_TRIGGER = re.compile(r'\b(?:BEFORE|AFTER|INSTEAD\s+OF)\s+DELETE\b', re.IGNORECASE)


def guarded_flush(connection, expected_name, original, sql_list):
    name = str(connection.settings_dict['NAME'])
    if connection.vendor != 'sqlite' or name != expected_name or not name.startswith('file:memorydb_'):
        raise RuntimeError('Guard cleanup requires the registered in-memory SQLite test database.')
    with transaction.atomic(using=connection.alias):
        with connection.cursor() as cursor:
            cursor.execute("SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND sql IS NOT NULL")
            triggers = [(name, sql) for name, sql in cursor.fetchall() if _DELETE_TRIGGER.search(sql)]
            for trigger, _ in triggers:
                cursor.execute('DROP TRIGGER ' + connection.ops.quote_name(trigger))
            try:
                original(sql_list)
            finally:
                for _, sql in triggers:
                    cursor.execute(sql)


class GuardedSQLiteRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        old_config = super().setup_databases(**kwargs)
        self._guard_flush_originals = []
        for alias in connections:
            connection = connections[alias]
            name = str(connection.settings_dict['NAME'])
            if connection.vendor != 'sqlite' or not name.startswith('file:memorydb_'):
                continue
            original = connection.ops.execute_sql_flush
            def flush(ops, sql_list, *, connection=connection, name=name, original=original):
                return guarded_flush(connection, name, original, sql_list)
            self._guard_flush_originals.append((connection.ops, original))
            connection.ops.execute_sql_flush = MethodType(flush, connection.ops)
        return old_config

    def teardown_databases(self, old_config, **kwargs):
        for ops, original in getattr(self, '_guard_flush_originals', []):
            ops.execute_sql_flush = original
        return super().teardown_databases(old_config, **kwargs)

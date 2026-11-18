# SPDX-License-Identifier: MPL-2.0
"""Protect existing customer history without rewriting rows.

SQLite table rebuilds must restore these triggers. Privileged database users and
PostgreSQL TRUNCATE can bypass ordinary row-level update/delete protections.
"""
from django.db import migrations


def forward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            editor.execute(
                f"CREATE TRIGGER customer_event_{operation.lower()} BEFORE {operation} ON customers_customerevent "
                "BEGIN SELECT RAISE(ABORT, 'Customer events are immutable'); END"
            )
    elif editor.connection.vendor == 'postgresql':
        editor.execute("""
            CREATE FUNCTION railet_customer_event_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Customer events are immutable'; END; $$;
            CREATE TRIGGER customer_event_immutable BEFORE UPDATE OR DELETE ON customers_customerevent
            FOR EACH ROW EXECUTE FUNCTION railet_customer_event_immutable();
        """)


def backward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('update', 'delete'):
            editor.execute(f'DROP TRIGGER IF EXISTS customer_event_{operation}')
    elif editor.connection.vendor == 'postgresql':
        editor.execute('DROP TRIGGER IF EXISTS customer_event_immutable ON customers_customerevent;')
        editor.execute('DROP FUNCTION IF EXISTS railet_customer_event_immutable();')


class Migration(migrations.Migration):
    dependencies = [('customers', '0009_mock_message_immutable')]
    operations = [migrations.RunPython(forward, backward)]

# SPDX-License-Identifier: MPL-2.0
"""Preserve deal history; row guards do not cover privileged access or TRUNCATE."""
from django.db import migrations


def forward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            editor.execute(f"CREATE TRIGGER deal_event_{operation.lower()} BEFORE {operation} ON deals_dealevent BEGIN SELECT RAISE(ABORT, 'Deal events are immutable'); END")
    elif editor.connection.vendor == 'postgresql':
        editor.execute("""
            CREATE FUNCTION railet_deal_event_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Deal events are immutable'; END; $$;
            CREATE TRIGGER deal_event_immutable BEFORE UPDATE OR DELETE ON deals_dealevent
            FOR EACH ROW EXECUTE FUNCTION railet_deal_event_immutable();
        """)
    else:
        raise RuntimeError('Deal event guards require SQLite or PostgreSQL')


def backward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('update', 'delete'):
            editor.execute(f'DROP TRIGGER IF EXISTS deal_event_{operation}')
    elif editor.connection.vendor == 'postgresql':
        editor.execute('DROP TRIGGER IF EXISTS deal_event_immutable ON deals_dealevent;')
        editor.execute('DROP FUNCTION IF EXISTS railet_deal_event_immutable();')


class Migration(migrations.Migration):
    dependencies = [('deals', '0016_followup_event_immutable')]
    operations = [migrations.RunPython(forward, backward)]

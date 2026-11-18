# SPDX-License-Identifier: MPL-2.0
"""Protect existing follow-up history without rewriting rows.

SQLite table rebuilds must restore these triggers. Privileged database users and
PostgreSQL TRUNCATE can bypass ordinary row-level update/delete protections.
"""
from django.db import migrations


def forward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            editor.execute(
                f"CREATE TRIGGER followup_event_{operation.lower()} BEFORE {operation} ON deals_followupevent "
                "BEGIN SELECT RAISE(ABORT, 'Deal follow-up events are immutable'); END"
            )
    elif editor.connection.vendor == 'postgresql':
        editor.execute("""
            CREATE FUNCTION railet_followup_event_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Deal follow-up events are immutable'; END; $$;
            CREATE TRIGGER followup_event_immutable BEFORE UPDATE OR DELETE ON deals_followupevent
            FOR EACH ROW EXECUTE FUNCTION railet_followup_event_immutable();
        """)


def backward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('update', 'delete'):
            editor.execute(f'DROP TRIGGER IF EXISTS followup_event_{operation}')
    elif editor.connection.vendor == 'postgresql':
        editor.execute('DROP TRIGGER IF EXISTS followup_event_immutable ON deals_followupevent;')
        editor.execute('DROP FUNCTION IF EXISTS railet_followup_event_immutable();')


class Migration(migrations.Migration):
    dependencies = [('deals', '0015_follow_on_draft_guards')]
    operations = [migrations.RunPython(forward, backward)]

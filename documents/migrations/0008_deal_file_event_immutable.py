# SPDX-License-Identifier: MPL-2.0
"""Preserve supporting-file history; row guards do not cover privileged access or TRUNCATE."""
from django.db import migrations


def forward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            editor.execute(f"CREATE TRIGGER deal_file_event_{operation.lower()} BEFORE {operation} ON documents_dealfileevent BEGIN SELECT RAISE(ABORT, 'Deal file events are immutable'); END")
    elif editor.connection.vendor == 'postgresql':
        editor.execute("""
            CREATE FUNCTION railet_deal_file_event_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Deal file events are immutable'; END; $$;
            CREATE TRIGGER deal_file_event_immutable BEFORE UPDATE OR DELETE ON documents_dealfileevent
            FOR EACH ROW EXECUTE FUNCTION railet_deal_file_event_immutable();
        """)
    else:
        raise RuntimeError('Deal file event guards require SQLite or PostgreSQL')


def backward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('update', 'delete'):
            editor.execute(f'DROP TRIGGER IF EXISTS deal_file_event_{operation}')
    elif editor.connection.vendor == 'postgresql':
        editor.execute('DROP TRIGGER IF EXISTS deal_file_event_immutable ON documents_dealfileevent;')
        editor.execute('DROP FUNCTION IF EXISTS railet_deal_file_event_immutable();')


class Migration(migrations.Migration):
    dependencies = [('documents', '0007_packet_export_event_immutable')]
    operations = [migrations.RunPython(forward, backward)]

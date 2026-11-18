# SPDX-License-Identifier: MPL-2.0
"""Preserve packet export history; row guards do not cover privileged access or TRUNCATE."""
from django.db import migrations


def forward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            editor.execute(f"CREATE TRIGGER packet_export_event_{operation.lower()} BEFORE {operation} ON documents_demopacketexportevent BEGIN SELECT RAISE(ABORT, 'Packet export events are immutable'); END")
    elif editor.connection.vendor == 'postgresql':
        editor.execute("""
            CREATE FUNCTION railet_packet_export_event_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Packet export events are immutable'; END; $$;
            CREATE TRIGGER packet_export_event_immutable BEFORE UPDATE OR DELETE ON documents_demopacketexportevent
            FOR EACH ROW EXECUTE FUNCTION railet_packet_export_event_immutable();
        """)
    else:
        raise RuntimeError('Packet export event guards require SQLite or PostgreSQL')


def backward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('update', 'delete'):
            editor.execute(f'DROP TRIGGER IF EXISTS packet_export_event_{operation}')
    elif editor.connection.vendor == 'postgresql':
        editor.execute('DROP TRIGGER IF EXISTS packet_export_event_immutable ON documents_demopacketexportevent;')
        editor.execute('DROP FUNCTION IF EXISTS railet_packet_export_event_immutable();')


class Migration(migrations.Migration):
    dependencies = [('documents', '0006_invoice_event_immutable')]
    operations = [migrations.RunPython(forward, backward)]

# SPDX-License-Identifier: MPL-2.0
"""Preserve invoice history; row guards do not cover privileged access or TRUNCATE."""
from django.db import migrations


def forward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            editor.execute(f"CREATE TRIGGER invoice_event_{operation.lower()} BEFORE {operation} ON documents_vehicleinvoiceevent BEGIN SELECT RAISE(ABORT, 'Invoice events are immutable'); END")
    elif editor.connection.vendor == 'postgresql':
        editor.execute("""
            CREATE FUNCTION railet_invoice_event_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Invoice events are immutable'; END; $$;
            CREATE TRIGGER invoice_event_immutable BEFORE UPDATE OR DELETE ON documents_vehicleinvoiceevent
            FOR EACH ROW EXECUTE FUNCTION railet_invoice_event_immutable();
        """)
    else:
        raise RuntimeError('Invoice event guards require SQLite or PostgreSQL')


def backward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('update', 'delete'):
            editor.execute(f'DROP TRIGGER IF EXISTS invoice_event_{operation}')
    elif editor.connection.vendor == 'postgresql':
        editor.execute('DROP TRIGGER IF EXISTS invoice_event_immutable ON documents_vehicleinvoiceevent;')
        editor.execute('DROP FUNCTION IF EXISTS railet_invoice_event_immutable();')


class Migration(migrations.Migration):
    dependencies = [('documents', '0005_vehicleacquisitionfile_vehicleacquisitionfileevent_and_more')]
    operations = [migrations.RunPython(forward, backward)]

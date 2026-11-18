# SPDX-License-Identifier: MPL-2.0
"""Preserve vendor history; row guards do not cover privileged access or TRUNCATE."""
from django.db import migrations


def forward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            editor.execute(f"CREATE TRIGGER vendor_event_{operation.lower()} BEFORE {operation} ON inventory_vehiclevendorevent BEGIN SELECT RAISE(ABORT, 'Vendor events are immutable'); END")
    elif editor.connection.vendor == 'postgresql':
        editor.execute("""
            CREATE FUNCTION railet_vendor_event_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Vendor events are immutable'; END; $$;
            CREATE TRIGGER vendor_event_immutable BEFORE UPDATE OR DELETE ON inventory_vehiclevendorevent
            FOR EACH ROW EXECUTE FUNCTION railet_vendor_event_immutable();
        """)
    else:
        raise RuntimeError('Vendor event guards require SQLite or PostgreSQL')


def backward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('update', 'delete'):
            editor.execute(f'DROP TRIGGER IF EXISTS vendor_event_{operation}')
    elif editor.connection.vendor == 'postgresql':
        editor.execute('DROP TRIGGER IF EXISTS vendor_event_immutable ON inventory_vehiclevendorevent;')
        editor.execute('DROP FUNCTION IF EXISTS railet_vendor_event_immutable();')


class Migration(migrations.Migration):
    dependencies = [('inventory', '0011_vehicle_sold_on')]
    operations = [migrations.RunPython(forward, backward)]

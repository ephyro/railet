# SPDX-License-Identifier: MPL-2.0
"""Protect new inventory audit records without rewriting historical rows."""
from django.db import migrations


def install_insert(cursor, vendor):
    if vendor == 'sqlite':
        cursor.execute("""CREATE TRIGGER inventory_audit_scope_insert
            BEFORE INSERT ON core_auditevent
            WHEN NOT EXISTS (SELECT 1 FROM inventory_vehicle v
                WHERE v.id = NEW.vehicle_id AND v.dealership_id = NEW.dealership_id)
            BEGIN SELECT RAISE(ABORT, 'Invalid inventory audit scope'); END""")
    elif vendor == 'postgresql':
        cursor.execute("""CREATE TRIGGER inventory_audit_scope_insert BEFORE INSERT ON core_auditevent
            FOR EACH ROW EXECUTE FUNCTION railet_inventory_audit_scope()""")
    else:
        raise RuntimeError('Inventory audit guards require SQLite or PostgreSQL.')


def drop_insert(cursor, vendor):
    if vendor == 'sqlite':
        cursor.execute('DROP TRIGGER IF EXISTS inventory_audit_scope_insert')
    elif vendor == 'postgresql':
        cursor.execute('DROP TRIGGER IF EXISTS inventory_audit_scope_insert ON core_auditevent')


def install(apps, editor):
    vendor = editor.connection.vendor
    if vendor == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            editor.execute(f"""CREATE TRIGGER inventory_audit_{operation.lower()} BEFORE {operation} ON core_auditevent
                BEGIN SELECT RAISE(ABORT, 'Inventory audit history is append-only'); END""")
        editor.execute("""CREATE TRIGGER inventory_audit_vehicle_owner BEFORE UPDATE OF dealership_id ON inventory_vehicle
            WHEN NEW.dealership_id != OLD.dealership_id AND EXISTS
                (SELECT 1 FROM core_auditevent a WHERE a.vehicle_id = OLD.id)
            BEGIN SELECT RAISE(ABORT, 'Vehicle with audit history cannot change dealership'); END""")
    elif vendor == 'postgresql':
        editor.execute("""CREATE FUNCTION railet_inventory_audit_scope() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE vehicle_dealer bigint;
        BEGIN
            SELECT dealership_id INTO vehicle_dealer FROM inventory_vehicle WHERE id = NEW.vehicle_id FOR UPDATE;
            IF NOT FOUND OR vehicle_dealer IS DISTINCT FROM NEW.dealership_id THEN
                RAISE EXCEPTION 'Invalid inventory audit scope';
            END IF;
            RETURN NEW;
        END; $$""")
        editor.execute("""CREATE FUNCTION railet_inventory_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Inventory audit history is append-only'; END; $$""")
        editor.execute("""CREATE TRIGGER inventory_audit_immutable BEFORE UPDATE OR DELETE ON core_auditevent
            FOR EACH ROW EXECUTE FUNCTION railet_inventory_audit_immutable()""")
        editor.execute("""CREATE FUNCTION railet_inventory_audit_vehicle_owner() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.dealership_id IS DISTINCT FROM OLD.dealership_id AND
               EXISTS (SELECT 1 FROM core_auditevent WHERE vehicle_id = OLD.id) THEN
                RAISE EXCEPTION 'Vehicle with audit history cannot change dealership';
            END IF;
            RETURN NEW;
        END; $$""")
        editor.execute("""CREATE TRIGGER inventory_audit_vehicle_owner BEFORE UPDATE OF dealership_id ON inventory_vehicle
            FOR EACH ROW EXECUTE FUNCTION railet_inventory_audit_vehicle_owner()""")
    else:
        raise RuntimeError('Inventory audit guards require SQLite or PostgreSQL.')
    with editor.connection.cursor() as cursor:
        install_insert(cursor, vendor)


def uninstall(apps, editor):
    vendor = editor.connection.vendor
    with editor.connection.cursor() as cursor:
        drop_insert(cursor, vendor)
    if vendor == 'sqlite':
        for name in ('inventory_audit_update', 'inventory_audit_delete', 'inventory_audit_vehicle_owner'):
            editor.execute(f'DROP TRIGGER IF EXISTS {name}')
    elif vendor == 'postgresql':
        editor.execute('DROP TRIGGER IF EXISTS inventory_audit_immutable ON core_auditevent')
        editor.execute('DROP TRIGGER IF EXISTS inventory_audit_vehicle_owner ON inventory_vehicle')
        for name in ('railet_inventory_audit_scope', 'railet_inventory_audit_immutable', 'railet_inventory_audit_vehicle_owner'):
            editor.execute(f'DROP FUNCTION IF EXISTS {name}()')
    else:
        raise RuntimeError('Inventory audit guards require SQLite or PostgreSQL.')


class Migration(migrations.Migration):
    dependencies = [('core', '0007_synthetic_mfa_event_immutable'), ('inventory', '0011_vehicle_sold_on')]
    operations = [migrations.RunPython(install, uninstall)]

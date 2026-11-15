# SPDX-License-Identifier: MPL-2.0
from django.db import migrations

# One row carries equal debit/credit control legs; not a general-ledger posting.
ACTOR = "EXISTS (SELECT 1 FROM core_membership m JOIN inventory_vehicle v ON v.dealership_id=m.dealership_id WHERE v.id=NEW.vehicle_id AND m.user_id=NEW.actor_id AND m.role IN ('owner','staff'))"
VENDOR = "NEW.vendor_id IS NULL OR EXISTS (SELECT 1 FROM inventory_vehiclevendor d JOIN inventory_vehicle v ON v.dealership_id=d.dealership_id WHERE v.id=NEW.vehicle_id AND d.id=NEW.vendor_id)"
TASK = "NEW.task_id IS NULL OR EXISTS (SELECT 1 FROM inventory_recontask t WHERE t.id=NEW.task_id AND t.vehicle_id=NEW.vehicle_id)"
REVERSAL = "NEW.kind <> 'reversal' OR EXISTS (SELECT 1 FROM inventory_vehiclecostentry s WHERE s.id=NEW.reverses_id AND s.kind='cost' AND s.vehicle_id=NEW.vehicle_id AND s.amount_cents=NEW.amount_cents AND s.category=NEW.category AND s.description=NEW.description AND (s.vendor_id=NEW.vendor_id OR (s.vendor_id IS NULL AND NEW.vendor_id IS NULL)) AND s.vendor_name=NEW.vendor_name AND (s.task_id=NEW.task_id OR (s.task_id IS NULL AND NEW.task_id IS NULL)) AND NEW.effective_on>=s.effective_on AND length(trim(NEW.reason))>0)"
TASK_VENDOR = "NEW.vendor_id IS NULL OR EXISTS (SELECT 1 FROM inventory_vehiclevendor d JOIN inventory_vehicle v ON v.dealership_id=d.dealership_id WHERE v.id=NEW.vehicle_id AND d.id=NEW.vendor_id)"


def forward(apps, editor):
    vendor = editor.connection.vendor
    if vendor == 'postgresql':
        editor.execute("""CREATE FUNCTION railet_cost_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Vehicle costs are append-only; use a linked reversal'; END; $$;
        CREATE TRIGGER vehicle_cost_immutable BEFORE UPDATE OR DELETE ON inventory_vehiclecostentry FOR EACH ROW EXECUTE FUNCTION railet_cost_immutable();""")
        condition = ' AND '.join(f'({part})' for part in [ACTOR, VENDOR, TASK, REVERSAL])
        editor.execute(f"""CREATE FUNCTION railet_cost_check() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        IF NOT ({condition}) THEN RAISE EXCEPTION 'Invalid vehicle cost scope or reversal'; END IF; RETURN NEW; END; $$;
        CREATE TRIGGER vehicle_cost_check BEFORE INSERT ON inventory_vehiclecostentry FOR EACH ROW EXECUTE FUNCTION railet_cost_check();""")
        editor.execute(f"""CREATE FUNCTION railet_recon_vendor_check() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        IF NOT ({TASK_VENDOR}) THEN RAISE EXCEPTION 'Vendor must belong to this dealership'; END IF; RETURN NEW; END; $$;
        CREATE TRIGGER recon_vendor_check BEFORE INSERT OR UPDATE ON inventory_recontask FOR EACH ROW EXECUTE FUNCTION railet_recon_vendor_check();""")
    elif vendor == 'sqlite':
        for operation in ['UPDATE', 'DELETE']:
            editor.execute(f"CREATE TRIGGER vehicle_cost_{operation.lower()} BEFORE {operation} ON inventory_vehiclecostentry BEGIN SELECT RAISE(ABORT, 'Vehicle costs are append-only'); END")
        condition = ' AND '.join(f'({part})' for part in [ACTOR, VENDOR, TASK, REVERSAL])
        editor.execute(f"CREATE TRIGGER vehicle_cost_check BEFORE INSERT ON inventory_vehiclecostentry WHEN NOT ({condition}) BEGIN SELECT RAISE(ABORT, 'Invalid vehicle cost scope or reversal'); END")
        for operation in ['INSERT', 'UPDATE']:
            editor.execute(f"CREATE TRIGGER recon_vendor_{operation.lower()} BEFORE {operation} ON inventory_recontask WHEN NOT ({TASK_VENDOR}) BEGIN SELECT RAISE(ABORT, 'Vendor must belong to this dealership'); END")
    else:
        raise RuntimeError('Vehicle cost guards require PostgreSQL or SQLite.')


def backward(apps, editor):
    if editor.connection.vendor == 'postgresql':
        editor.execute('DROP TRIGGER recon_vendor_check ON inventory_recontask; DROP FUNCTION railet_recon_vendor_check(); DROP TRIGGER vehicle_cost_check ON inventory_vehiclecostentry; DROP FUNCTION railet_cost_check(); DROP TRIGGER vehicle_cost_immutable ON inventory_vehiclecostentry; DROP FUNCTION railet_cost_immutable();')
    elif editor.connection.vendor == 'sqlite':
        for name in ['vehicle_cost_update', 'vehicle_cost_delete', 'vehicle_cost_check', 'recon_vendor_insert', 'recon_vendor_update']:
            editor.execute(f'DROP TRIGGER {name}')


class Migration(migrations.Migration):
    dependencies = [('inventory', '0005_recontask_vehiclevendor_vehiclecostentry_and_more')]
    operations = [migrations.RunPython(forward, backward)]

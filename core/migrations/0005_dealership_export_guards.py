# SPDX-License-Identifier: MPL-2.0
from django.db import migrations


def forwards(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            editor.execute(f"CREATE TRIGGER dealership_export_event_{operation.lower()} BEFORE {operation} ON core_dealershipexportevent BEGIN SELECT RAISE(ABORT, 'Dealership export audit is immutable'); END")
        editor.execute("""CREATE TRIGGER dealership_export_event_check BEFORE INSERT ON core_dealershipexportevent
            WHEN NOT EXISTS (SELECT 1 FROM core_membership m WHERE m.user_id=NEW.actor_id
              AND m.dealership_id=NEW.dealership_id AND m.role='owner')
            BEGIN SELECT RAISE(ABORT, 'Owner membership required'); END""")
    elif editor.connection.vendor == 'postgresql':
        editor.execute("""CREATE FUNCTION railet_dealership_export_event_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Dealership export audit is immutable'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_membership m WHERE m.user_id=NEW.actor_id
            AND m.dealership_id=NEW.dealership_id AND m.role='owner') THEN RAISE EXCEPTION 'Owner membership required'; END IF;
          RETURN NEW;
        END; $$;
        CREATE TRIGGER dealership_export_event_guard BEFORE INSERT OR UPDATE OR DELETE ON core_dealershipexportevent
          FOR EACH ROW EXECUTE FUNCTION railet_dealership_export_event_guard();""")


def backwards(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for name in ('update', 'delete', 'check'):
            editor.execute(f'DROP TRIGGER dealership_export_event_{name}')
    elif editor.connection.vendor == 'postgresql':
        editor.execute('DROP TRIGGER dealership_export_event_guard ON core_dealershipexportevent; DROP FUNCTION railet_dealership_export_event_guard();')


class Migration(migrations.Migration):
    dependencies = [('core', '0004_dealershipexportevent')]
    operations = [migrations.RunPython(forwards, backwards)]

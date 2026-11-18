# SPDX-License-Identifier: MPL-2.0
from django.db import migrations


def forwards(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            editor.execute(f"CREATE TRIGGER customer_export_event_{operation.lower()} BEFORE {operation} ON customers_customerexportevent BEGIN SELECT RAISE(ABORT, 'Customer export audit is immutable'); END")
        editor.execute("""CREATE TRIGGER customer_export_event_check BEFORE INSERT ON customers_customerexportevent
            WHEN NOT EXISTS (SELECT 1 FROM core_membership m WHERE m.user_id=NEW.actor_id
                AND m.dealership_id=NEW.dealership_id AND m.role='owner')
            BEGIN SELECT RAISE(ABORT, 'Owner membership required'); END""")
    elif editor.connection.vendor == 'postgresql':
        editor.execute("""
        CREATE FUNCTION railet_customer_export_event_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Customer export audit is immutable'; END IF;
            IF NOT EXISTS (SELECT 1 FROM core_membership m WHERE m.user_id=NEW.actor_id
                AND m.dealership_id=NEW.dealership_id AND m.role='owner')
                THEN RAISE EXCEPTION 'Owner membership required'; END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER customer_export_event_guard BEFORE INSERT OR UPDATE OR DELETE
        ON customers_customerexportevent FOR EACH ROW EXECUTE FUNCTION railet_customer_export_event_guard();
        """)


def backwards(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for name in ('update', 'delete', 'check'):
            editor.execute(f'DROP TRIGGER customer_export_event_{name}')
    elif editor.connection.vendor == 'postgresql':
        editor.execute('DROP TRIGGER customer_export_event_guard ON customers_customerexportevent; DROP FUNCTION railet_customer_export_event_guard();')


class Migration(migrations.Migration):
    dependencies = [('customers', '0006_customerexportevent')]
    operations = [migrations.RunPython(forwards, backwards)]

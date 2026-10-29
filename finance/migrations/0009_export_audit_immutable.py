# SPDX-License-Identifier: MPL-2.0
from django.db import migrations


def forwards(apps,schema_editor):
    if schema_editor.connection.vendor=='postgresql':
        schema_editor.execute('''
CREATE TRIGGER demo_account_export_immutable BEFORE UPDATE OR DELETE ON finance_demoaccountexport FOR EACH ROW EXECUTE FUNCTION railet_demo_immutable();
CREATE FUNCTION railet_demo_account_export_check() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM finance_demobook b JOIN core_membership m ON m.dealership_id=b.dealership_id JOIN customers_customer c ON c.id=b.customer_id WHERE b.id=NEW.book_id AND c.dealership_id=b.dealership_id AND m.user_id=NEW.actor_id AND m.role IN ('owner','staff','viewer')) THEN RAISE EXCEPTION 'Authorized dealership actor required'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER demo_account_export_check BEFORE INSERT ON finance_demoaccountexport FOR EACH ROW EXECUTE FUNCTION railet_demo_account_export_check();
''')
    elif schema_editor.connection.vendor=='sqlite':
        for operation in ('UPDATE','DELETE'):
            schema_editor.execute(f"CREATE TRIGGER demo_account_export_{operation.lower()} BEFORE {operation} ON finance_demoaccountexport BEGIN SELECT RAISE(ABORT, 'Export audit is immutable'); END")


def backwards(apps,schema_editor):
    if schema_editor.connection.vendor=='postgresql':
        schema_editor.execute('DROP TRIGGER demo_account_export_check ON finance_demoaccountexport; DROP FUNCTION railet_demo_account_export_check(); DROP TRIGGER demo_account_export_immutable ON finance_demoaccountexport;')
    elif schema_editor.connection.vendor=='sqlite':
        for operation in ('update','delete'):schema_editor.execute(f'DROP TRIGGER demo_account_export_{operation}')


class Migration(migrations.Migration):
    dependencies=[('finance','0008_demoaccountexport')]
    operations=[migrations.RunPython(forwards,backwards)]

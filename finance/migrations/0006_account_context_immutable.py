# SPDX-License-Identifier: MPL-2.0
from django.db import migrations


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('''
CREATE TRIGGER demo_account_context_immutable BEFORE UPDATE OR DELETE ON finance_demoaccountcontext FOR EACH ROW EXECUTE FUNCTION railet_demo_immutable();
CREATE FUNCTION railet_demo_account_context_check() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS (
 SELECT 1 FROM finance_demobook b JOIN deals_draftdeal d ON d.id=NEW.deal_id
 JOIN customers_customer c ON c.id=b.customer_id
 JOIN inventory_vehicle v ON v.id=d.vehicle_id
 JOIN core_membership m ON m.user_id=NEW.created_by_id AND m.dealership_id=b.dealership_id
 WHERE b.id=NEW.book_id AND d.dealership_id=b.dealership_id AND d.buyer_id=b.customer_id
 AND c.dealership_id=b.dealership_id AND v.dealership_id=b.dealership_id
 AND d.deal_type='bhph' AND d.archived_at IS NULL AND m.role IN ('owner','staff')
 ) THEN RAISE EXCEPTION 'An authorized matching BHPH draft is required'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER demo_account_context_check BEFORE INSERT ON finance_demoaccountcontext FOR EACH ROW EXECUTE FUNCTION railet_demo_account_context_check();
''')
    elif schema_editor.connection.vendor == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            schema_editor.execute(f"CREATE TRIGGER demo_account_context_{operation.lower()} BEFORE {operation} ON finance_demoaccountcontext BEGIN SELECT RAISE(ABORT, 'Saved account context is immutable'); END")


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('DROP TRIGGER demo_account_context_check ON finance_demoaccountcontext; DROP FUNCTION railet_demo_account_context_check(); DROP TRIGGER demo_account_context_immutable ON finance_demoaccountcontext;')
    elif schema_editor.connection.vendor == 'sqlite':
        for operation in ('update', 'delete'):
            schema_editor.execute(f'DROP TRIGGER demo_account_context_{operation}')


class Migration(migrations.Migration):
    dependencies = [('finance', '0005_demoaccountcontext')]
    operations = [migrations.RunPython(forwards, backwards)]

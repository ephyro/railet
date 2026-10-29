# SPDX-License-Identifier: MPL-2.0
from django.db import migrations,models


def forwards(apps,schema_editor):
    if schema_editor.connection.vendor=='postgresql':
        schema_editor.execute("""
CREATE TRIGGER demo_servicing_immutable BEFORE UPDATE OR DELETE ON finance_demoservicingplan FOR EACH ROW EXECUTE FUNCTION railet_demo_immutable();
CREATE FUNCTION railet_demo_servicing_check() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF length(trim(NEW.reason))=0 OR NOT EXISTS (
 SELECT 1 FROM finance_demobook b JOIN finance_demoschedule s ON s.book_id=b.id
 JOIN customers_customer c ON c.id=b.customer_id
 JOIN core_membership m ON m.user_id=NEW.created_by_id AND m.dealership_id=b.dealership_id
 WHERE b.id=NEW.book_id AND s.id=NEW.schedule_id AND s.method='precomputed'
 AND s.inputs->>'frequency'='monthly' AND s.result_sha256=NEW.schedule_sha256
 AND c.dealership_id=b.dealership_id AND m.role IN ('owner','staff')
 ) THEN RAISE EXCEPTION 'Authorized matching monthly precomputed baseline required'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER demo_servicing_check BEFORE INSERT ON finance_demoservicingplan FOR EACH ROW EXECUTE FUNCTION railet_demo_servicing_check();
""")
    elif schema_editor.connection.vendor=='sqlite':
        for operation in ('UPDATE','DELETE'):
            schema_editor.execute(f"CREATE TRIGGER demo_servicing_{operation.lower()} BEFORE {operation} ON finance_demoservicingplan BEGIN SELECT RAISE(ABORT, 'Saved servicing baseline is immutable'); END")
        schema_editor.execute("""CREATE TRIGGER demo_servicing_check BEFORE INSERT ON finance_demoservicingplan WHEN length(trim(NEW.reason))=0 OR NOT EXISTS (
 SELECT 1 FROM finance_demobook b JOIN finance_demoschedule s ON s.book_id=b.id
 JOIN customers_customer c ON c.id=b.customer_id
 JOIN core_membership m ON m.user_id=NEW.created_by_id AND m.dealership_id=b.dealership_id
 WHERE b.id=NEW.book_id AND s.id=NEW.schedule_id AND s.method='precomputed'
 AND json_extract(s.inputs,'$.frequency')='monthly' AND s.result_sha256=NEW.schedule_sha256
 AND c.dealership_id=b.dealership_id AND m.role IN ('owner','staff'))
 BEGIN SELECT RAISE(ABORT, 'Authorized matching monthly precomputed baseline required'); END""")


def backwards(apps,schema_editor):
    if schema_editor.connection.vendor=='postgresql':
        schema_editor.execute('DROP TRIGGER demo_servicing_check ON finance_demoservicingplan; DROP FUNCTION railet_demo_servicing_check(); DROP TRIGGER demo_servicing_immutable ON finance_demoservicingplan;')
    elif schema_editor.connection.vendor=='sqlite':
        for name in ('update','delete','check'):schema_editor.execute(f'DROP TRIGGER demo_servicing_{name}')


class Migration(migrations.Migration):
    dependencies=[('finance','0011_demo_servicing_plan')]
    operations=[migrations.RunPython(forwards,backwards),migrations.AlterField(model_name='demoaccountexport',name='format_version',field=models.CharField(default='demo-account-export-v3',max_length=40))]

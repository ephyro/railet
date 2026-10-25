# SPDX-License-Identifier: MPL-2.0
from django.db import migrations


def forwards(apps,schema_editor):
    if schema_editor.connection.vendor=='postgresql':
        schema_editor.execute("""
CREATE TRIGGER demo_schedule_immutable BEFORE UPDATE OR DELETE ON finance_demoschedule FOR EACH ROW EXECUTE FUNCTION railet_demo_immutable();
CREATE FUNCTION railet_demo_schedule_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE dealer bigint;
BEGIN
 SELECT dealership_id INTO dealer FROM finance_demobook WHERE id=NEW.book_id;
 IF NOT EXISTS (SELECT 1 FROM core_membership WHERE user_id=NEW.created_by_id AND dealership_id=dealer AND role IN ('owner','staff')) THEN RAISE EXCEPTION 'Authorized dealership actor required'; END IF;
 IF NEW.method IS DISTINCT FROM NEW.result->>'method' OR NEW.calculation_version IS DISTINCT FROM NEW.result->>'calculation_version' THEN RAISE EXCEPTION 'Illustration metadata does not match result'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER demo_schedule_check BEFORE INSERT ON finance_demoschedule FOR EACH ROW EXECUTE FUNCTION railet_demo_schedule_check();
""")
    elif schema_editor.connection.vendor=='sqlite':
        for operation in ('UPDATE','DELETE'):
            schema_editor.execute(f"CREATE TRIGGER demo_schedule_{operation.lower()} BEFORE {operation} ON finance_demoschedule BEGIN SELECT RAISE(ABORT, 'Saved illustrations are immutable'); END")


def backwards(apps,schema_editor):
    if schema_editor.connection.vendor=='postgresql':
        schema_editor.execute('DROP TRIGGER demo_schedule_check ON finance_demoschedule; DROP FUNCTION railet_demo_schedule_check(); DROP TRIGGER demo_schedule_immutable ON finance_demoschedule;')
    elif schema_editor.connection.vendor=='sqlite':
        for operation in ('update','delete'):schema_editor.execute(f'DROP TRIGGER demo_schedule_{operation}')


class Migration(migrations.Migration):
    dependencies=[('finance','0003_demoschedule')]
    operations=[migrations.RunPython(forwards,backwards)]

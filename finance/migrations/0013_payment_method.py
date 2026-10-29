# SPDX-License-Identifier: MPL-2.0
from django.db import migrations,models


def add_column(apps,schema_editor):
    # ALTER ADD preserves append-only triggers on SQLite; no table recreation.
    schema_editor.execute("ALTER TABLE finance_demoposting ADD COLUMN payment_method varchar(16) NOT NULL DEFAULT 'unspecified'")
    if schema_editor.connection.vendor=='postgresql':
        schema_editor.execute("ALTER TABLE finance_demoposting ALTER COLUMN payment_method DROP DEFAULT")
        schema_editor.execute("""
CREATE FUNCTION railet_demo_payment_method_check() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.payment_method NOT IN ('unspecified','cash','check','other')
 OR (NEW.kind='opening' AND NEW.payment_method <> 'unspecified')
 OR (NEW.kind='reversal' AND NOT EXISTS (SELECT 1 FROM finance_demoposting p WHERE p.id=NEW.reverses_id AND p.payment_method=NEW.payment_method))
 THEN RAISE EXCEPTION 'Valid receipt method and matching reversal required'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER demo_payment_method_check BEFORE INSERT ON finance_demoposting FOR EACH ROW EXECUTE FUNCTION railet_demo_payment_method_check();
""")
    elif schema_editor.connection.vendor=='sqlite':
        schema_editor.execute("""CREATE TRIGGER demo_payment_method_check BEFORE INSERT ON finance_demoposting
WHEN NEW.payment_method NOT IN ('unspecified','cash','check','other') OR (NEW.kind='opening' AND NEW.payment_method <> 'unspecified')
OR (NEW.kind='reversal' AND NOT EXISTS (SELECT 1 FROM finance_demoposting p WHERE p.id=NEW.reverses_id AND p.payment_method=NEW.payment_method))
BEGIN SELECT RAISE(ABORT, 'Valid receipt method and matching reversal required'); END""")


def remove_column(apps,schema_editor):
    if schema_editor.connection.vendor=='postgresql':
        schema_editor.execute('DROP TRIGGER demo_payment_method_check ON finance_demoposting; DROP FUNCTION railet_demo_payment_method_check();')
    elif schema_editor.connection.vendor=='sqlite':schema_editor.execute('DROP TRIGGER demo_payment_method_check')
    schema_editor.execute('ALTER TABLE finance_demoposting DROP COLUMN payment_method')


class Migration(migrations.Migration):
    dependencies=[('finance','0012_servicing_guards_export_version')]
    operations=[migrations.SeparateDatabaseAndState(
        database_operations=[migrations.RunPython(add_column,remove_column)],
        state_operations=[migrations.AddField(model_name='demoposting',name='payment_method',field=models.CharField(max_length=16,choices=[('unspecified','Not recorded'),('cash','Cash'),('check','Check'),('other','Other')],default='unspecified'))]),
        migrations.AlterField(model_name='demoaccountexport',name='format_version',field=models.CharField(default='demo-account-export-v4',max_length=40))]

# SPDX-License-Identifier: MPL-2.0
from django.db import migrations


POSTGRES = """
CREATE FUNCTION railet_demo_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Synthetic ledger records are append-only; use a linked correction'; END;
$$;
CREATE TRIGGER demo_book_immutable BEFORE UPDATE OR DELETE ON finance_demobook FOR EACH ROW EXECUTE FUNCTION railet_demo_immutable();
CREATE TRIGGER demo_posting_immutable BEFORE UPDATE OR DELETE ON finance_demoposting FOR EACH ROW EXECUTE FUNCTION railet_demo_immutable();
CREATE FUNCTION railet_demo_book_check() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM customers_customer WHERE id=NEW.customer_id AND dealership_id=NEW.dealership_id) THEN RAISE EXCEPTION 'Customer must belong to the same dealership'; END IF;
 IF NOT EXISTS (SELECT 1 FROM core_membership WHERE user_id=NEW.created_by_id AND dealership_id=NEW.dealership_id AND role IN ('owner','staff')) THEN RAISE EXCEPTION 'Authorized dealership actor required'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER demo_book_check BEFORE INSERT ON finance_demobook FOR EACH ROW EXECUTE FUNCTION railet_demo_book_check();
CREATE FUNCTION railet_demo_posting_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE source RECORD; opened date; dealer bigint;
BEGIN
 SELECT opening_on,dealership_id INTO opened,dealer FROM finance_demobook WHERE id=NEW.book_id;
 IF NEW.effective_on < opened THEN RAISE EXCEPTION 'Posting predates opening'; END IF;
 IF NOT EXISTS (SELECT 1 FROM core_membership WHERE user_id=NEW.actor_id AND dealership_id=dealer AND role IN ('owner','staff')) THEN RAISE EXCEPTION 'Authorized dealership actor required'; END IF;
 IF NEW.kind='reversal' THEN
  SELECT * INTO source FROM finance_demoposting WHERE id=NEW.reverses_id;
  IF source.id IS NULL OR source.kind <> 'receipt' OR source.book_id <> NEW.book_id OR source.amount_cents <> NEW.amount_cents OR NEW.effective_on < source.effective_on THEN RAISE EXCEPTION 'Invalid linked receipt reversal'; END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER demo_posting_check BEFORE INSERT ON finance_demoposting FOR EACH ROW EXECUTE FUNCTION railet_demo_posting_check();
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(POSTGRES)
    elif schema_editor.connection.vendor == 'sqlite':
        for table, prefix in [('finance_demobook','demo_book'),('finance_demoposting','demo_posting')]:
            for operation in ('UPDATE','DELETE'):
                schema_editor.execute(f"CREATE TRIGGER {prefix}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'Synthetic ledger records are append-only'); END")


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('DROP TRIGGER demo_posting_check ON finance_demoposting; DROP TRIGGER demo_book_check ON finance_demobook; DROP TRIGGER demo_posting_immutable ON finance_demoposting; DROP TRIGGER demo_book_immutable ON finance_demobook; DROP FUNCTION railet_demo_posting_check(); DROP FUNCTION railet_demo_book_check(); DROP FUNCTION railet_demo_immutable();')
    elif schema_editor.connection.vendor == 'sqlite':
        for prefix in ('demo_book','demo_posting'):
            for operation in ('update','delete'):
                schema_editor.execute(f'DROP TRIGGER {prefix}_{operation}')


class Migration(migrations.Migration):
    dependencies = [('finance','0001_initial')]
    operations = [migrations.RunPython(forwards,backwards)]

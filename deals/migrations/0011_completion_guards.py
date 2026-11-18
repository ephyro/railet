# SPDX-License-Identifier: MPL-2.0
from django.db import migrations

TABLES = [('deals_draftdeal','id'),('deals_draftfinanceproposal','deal_id'),('deals_drafttradein','deal_id'),('deals_dealevent','deal_id')]
CHECK = "EXISTS (SELECT 1 FROM deals_draftdeal d JOIN documents_demodealpacket p ON p.deal_id=d.id JOIN core_membership m ON m.dealership_id=d.dealership_id WHERE d.id=NEW.deal_id AND d.archived_at IS NULL AND d.revision=NEW.source_revision AND p.id=NEW.packet_id AND p.created_by_id=NEW.actor_id AND p.source_sha256=NEW.source_sha256 AND p.artifact_sha256=NEW.artifact_sha256 AND m.user_id=NEW.actor_id AND m.role IN ('owner','staff'))"


def forward(apps, editor):
    if editor.connection.vendor=='postgresql':
        editor.execute("""CREATE FUNCTION railet_completion_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Completed rehearsal records are immutable'; END; $$;
        CREATE TRIGGER completion_immutable BEFORE UPDATE OR DELETE ON deals_demodealcompletion FOR EACH ROW EXECUTE FUNCTION railet_completion_immutable();""")
        editor.execute(f"""CREATE FUNCTION railet_completion_check() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        PERFORM id FROM deals_draftdeal WHERE id=NEW.deal_id FOR UPDATE;
        IF NOT ({CHECK}) THEN RAISE EXCEPTION 'Invalid completion actor or packet'; END IF; RETURN NEW; END; $$;
        CREATE TRIGGER completion_check BEFORE INSERT ON deals_demodealcompletion FOR EACH ROW EXECUTE FUNCTION railet_completion_check();""")
        for table, field in TABLES:
            prefix=table.removeprefix('deals_')
            # Events can be appended after completion, but cannot be rewritten.
            operations=['UPDATE','DELETE'] if field=='id' or table=='deals_dealevent' else ['INSERT','UPDATE','DELETE']
            editor.execute(f"""CREATE FUNCTION railet_freeze_{prefix}() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE parent bigint; BEGIN
            IF TG_OP='DELETE' THEN parent=OLD.{field}; ELSE parent=NEW.{field}; END IF;
            PERFORM id FROM deals_draftdeal WHERE id=parent FOR UPDATE;
            IF EXISTS (SELECT 1 FROM deals_demodealcompletion WHERE deal_id=parent) THEN RAISE EXCEPTION 'Completed rehearsal source is frozen'; END IF;
            IF TG_OP='UPDATE' AND {('TRUE' if field=='deal_id' else 'FALSE')} THEN
              IF EXISTS (SELECT 1 FROM deals_demodealcompletion WHERE deal_id=OLD.{field}) THEN RAISE EXCEPTION 'Completed rehearsal source is frozen'; END IF;
            END IF;
            IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END; $$;
            CREATE TRIGGER completion_freeze_{prefix} BEFORE {' OR '.join(operations)} ON {table} FOR EACH ROW EXECUTE FUNCTION railet_freeze_{prefix}();""")
        editor.execute("""CREATE FUNCTION railet_completion_packet_freeze() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        IF EXISTS (SELECT 1 FROM deals_demodealcompletion WHERE packet_id=OLD.id) THEN RAISE EXCEPTION 'Completed rehearsal packet is frozen'; END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END; $$;
        CREATE TRIGGER completion_packet_freeze BEFORE UPDATE OR DELETE ON documents_demodealpacket FOR EACH ROW EXECUTE FUNCTION railet_completion_packet_freeze();""")
    elif editor.connection.vendor=='sqlite':
        for op in ['UPDATE','DELETE']:
            editor.execute(f"CREATE TRIGGER completion_{op.lower()} BEFORE {op} ON deals_demodealcompletion BEGIN SELECT RAISE(ABORT,'Completed rehearsal records are immutable'); END")
        editor.execute(f"CREATE TRIGGER completion_check BEFORE INSERT ON deals_demodealcompletion WHEN NOT ({CHECK}) BEGIN SELECT RAISE(ABORT,'Invalid completion actor or packet'); END")
        for table, field in TABLES:
            prefix=table.removeprefix('deals_')
            operations=['UPDATE','DELETE'] if field=='id' or table=='deals_dealevent' else ['INSERT','UPDATE','DELETE']
            for op in operations:
                parent=f'OLD.{field}' if op=='DELETE' else f'NEW.{field}'
                condition=f'EXISTS (SELECT 1 FROM deals_demodealcompletion WHERE deal_id={parent})'
                if op=='UPDATE' and field=='deal_id':
                    condition+=f' OR EXISTS (SELECT 1 FROM deals_demodealcompletion WHERE deal_id=OLD.{field})'
                editor.execute(f"CREATE TRIGGER completion_freeze_{prefix}_{op.lower()} BEFORE {op} ON {table} WHEN {condition} BEGIN SELECT RAISE(ABORT,'Completed rehearsal source is frozen'); END")
        for op in ['UPDATE','DELETE']:
            editor.execute(f"CREATE TRIGGER completion_packet_{op.lower()} BEFORE {op} ON documents_demodealpacket WHEN EXISTS (SELECT 1 FROM deals_demodealcompletion WHERE packet_id=OLD.id) BEGIN SELECT RAISE(ABORT,'Completed rehearsal packet is frozen'); END")
    else:
        raise RuntimeError('Completion guards require PostgreSQL or SQLite.')


def backward(apps, editor):
    if editor.connection.vendor=='postgresql':
        editor.execute('DROP TRIGGER completion_packet_freeze ON documents_demodealpacket; DROP FUNCTION railet_completion_packet_freeze(); DROP TRIGGER completion_check ON deals_demodealcompletion; DROP FUNCTION railet_completion_check(); DROP TRIGGER completion_immutable ON deals_demodealcompletion; DROP FUNCTION railet_completion_immutable();')
        for table,_ in TABLES:
            prefix=table.removeprefix('deals_')
            editor.execute(f'DROP TRIGGER completion_freeze_{prefix} ON {table}; DROP FUNCTION railet_freeze_{prefix}();')
    elif editor.connection.vendor=='sqlite':
        names=['completion_update','completion_delete','completion_check','completion_packet_update','completion_packet_delete']
        for table,field in TABLES:
            prefix=table.removeprefix('deals_')
            operations=['update','delete'] if field=='id' or table=='deals_dealevent' else ['insert','update','delete']
            names.extend(f'completion_freeze_{prefix}_{op}' for op in operations)
        for name in names:editor.execute(f'DROP TRIGGER {name}')


class Migration(migrations.Migration):
    dependencies=[('deals','0010_demodealcompletion')]
    operations=[migrations.RunPython(forward,backward)]

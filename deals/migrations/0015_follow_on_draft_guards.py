# SPDX-License-Identifier: MPL-2.0
from django.db import migrations

CHECK = (
    "NEW.policy_version = 'demo-follow-on-draft-v1' "
    "AND EXISTS ("
    "SELECT 1 FROM deals_democompletionvoid v "
    "JOIN deals_demodealcompletion c ON c.id = v.completion_id "
    "JOIN deals_draftdeal src ON src.id = c.deal_id "
    "JOIN deals_draftdeal dst ON dst.id = NEW.draft_id "
    "JOIN core_membership m ON m.dealership_id = src.dealership_id "
    "WHERE v.id = NEW.void_rehearsal_id "
    "AND dst.id <> src.id "
    "AND dst.dealership_id = src.dealership_id "
    "AND m.user_id = NEW.actor_id AND m.role IN ('owner', 'staff')"
    ")"
)


def forward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for op in ('UPDATE', 'DELETE'):
            editor.execute(f"CREATE TRIGGER follow_on_draft_{op.lower()} BEFORE {op} ON deals_demofollowondraft BEGIN SELECT RAISE(ABORT, 'Follow-on draft provenance is immutable'); END")
        editor.execute(f"CREATE TRIGGER follow_on_draft_check BEFORE INSERT ON deals_demofollowondraft WHEN NOT ({CHECK}) BEGIN SELECT RAISE(ABORT, 'Invalid follow-on draft provenance'); END")
    elif editor.connection.vendor == 'postgresql':
        editor.execute("""CREATE FUNCTION railet_follow_on_draft_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Follow-on draft provenance is immutable'; END; $$;
            CREATE TRIGGER follow_on_draft_immutable BEFORE UPDATE OR DELETE ON deals_demofollowondraft FOR EACH ROW EXECUTE FUNCTION railet_follow_on_draft_immutable();""")
        editor.execute(f"""CREATE FUNCTION railet_follow_on_draft_check() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            IF NOT ({CHECK}) THEN RAISE EXCEPTION 'Invalid follow-on draft provenance'; END IF; RETURN NEW; END; $$;
            CREATE TRIGGER follow_on_draft_check BEFORE INSERT ON deals_demofollowondraft FOR EACH ROW EXECUTE FUNCTION railet_follow_on_draft_check();""")
    else:
        raise RuntimeError('Follow-on draft guards require SQLite or PostgreSQL.')


def backward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for name in ('follow_on_draft_update', 'follow_on_draft_delete', 'follow_on_draft_check'):
            editor.execute(f'DROP TRIGGER {name}')
    elif editor.connection.vendor == 'postgresql':
        editor.execute('DROP TRIGGER follow_on_draft_check ON deals_demofollowondraft; DROP FUNCTION railet_follow_on_draft_check(); DROP TRIGGER follow_on_draft_immutable ON deals_demofollowondraft; DROP FUNCTION railet_follow_on_draft_immutable();')


class Migration(migrations.Migration):
    dependencies = [('deals', '0014_demofollowondraft')]
    operations = [migrations.RunPython(forward, backward)]

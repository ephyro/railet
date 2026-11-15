# SPDX-License-Identifier: MPL-2.0
from django.db import migrations


def forward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for op in ('UPDATE', 'DELETE'):
            editor.execute(f"CREATE TRIGGER completion_void_{op.lower()} BEFORE {op} ON deals_democompletionvoid BEGIN SELECT RAISE(ABORT, 'Void rehearsal is immutable'); END")
    elif editor.connection.vendor == 'postgresql':
        editor.execute("""CREATE FUNCTION railet_completion_void_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Void rehearsal is immutable'; END; $$;
            CREATE TRIGGER completion_void_immutable BEFORE UPDATE OR DELETE ON deals_democompletionvoid FOR EACH ROW EXECUTE FUNCTION railet_completion_void_immutable();""")
    else:
        raise RuntimeError('Void guards require SQLite or PostgreSQL.')


def backward(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for op in ('update', 'delete'):
            editor.execute(f'DROP TRIGGER completion_void_{op}')
    elif editor.connection.vendor == 'postgresql':
        editor.execute('DROP TRIGGER completion_void_immutable ON deals_democompletionvoid; DROP FUNCTION railet_completion_void_immutable();')


class Migration(migrations.Migration):
    dependencies = [('deals', '0012_democompletionvoid')]
    operations = [migrations.RunPython(forward, backward)]

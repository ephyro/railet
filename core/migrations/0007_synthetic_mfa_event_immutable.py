# SPDX-License-Identifier: MPL-2.0
from django.db import migrations


def install(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            editor.execute(f"CREATE TRIGGER synthetic_mfa_event_{operation.lower()} BEFORE {operation} ON core_syntheticmfaevent BEGIN SELECT RAISE(ABORT, 'Synthetic MFA history is immutable'); END")
    elif editor.connection.vendor == 'postgresql':
        editor.execute("""CREATE FUNCTION railet_synthetic_mfa_event_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Synthetic MFA history is immutable'; END; $$""")
        editor.execute('CREATE TRIGGER synthetic_mfa_event_immutable BEFORE UPDATE OR DELETE ON core_syntheticmfaevent FOR EACH ROW EXECUTE FUNCTION railet_synthetic_mfa_event_immutable()')
    else:
        raise RuntimeError('Synthetic MFA history guards require SQLite or PostgreSQL.')


def uninstall(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            editor.execute(f'DROP TRIGGER IF EXISTS synthetic_mfa_event_{operation.lower()}')
    elif editor.connection.vendor == 'postgresql':
        editor.execute('DROP TRIGGER IF EXISTS synthetic_mfa_event_immutable ON core_syntheticmfaevent')
        editor.execute('DROP FUNCTION IF EXISTS railet_synthetic_mfa_event_immutable()')


class Migration(migrations.Migration):
    dependencies = [('core', '0006_syntheticmfafactor_syntheticmfaevent')]
    operations = [migrations.RunPython(install, uninstall)]

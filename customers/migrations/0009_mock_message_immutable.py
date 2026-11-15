# SPDX-License-Identifier: MPL-2.0
from django.db import migrations


def forwards(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for table in ('mockmessagesubmission', 'mockmessageevent'):
            for operation in ('UPDATE', 'DELETE'):
                editor.execute(f"CREATE TRIGGER {table}_{operation.lower()} BEFORE {operation} ON customers_{table} BEGIN SELECT RAISE(ABORT, 'Mock message history is immutable'); END")
    elif editor.connection.vendor == 'postgresql':
        editor.execute("""CREATE FUNCTION railet_mock_message_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Mock message history is immutable'; END; $$;
        CREATE TRIGGER mockmessagesubmission_immutable BEFORE UPDATE OR DELETE ON customers_mockmessagesubmission FOR EACH ROW EXECUTE FUNCTION railet_mock_message_immutable();
        CREATE TRIGGER mockmessageevent_immutable BEFORE UPDATE OR DELETE ON customers_mockmessageevent FOR EACH ROW EXECUTE FUNCTION railet_mock_message_immutable();""")


def backwards(apps, editor):
    if editor.connection.vendor == 'sqlite':
        for table in ('mockmessagesubmission', 'mockmessageevent'):
            for operation in ('update', 'delete'):
                editor.execute(f'DROP TRIGGER {table}_{operation}')
    elif editor.connection.vendor == 'postgresql':
        editor.execute('DROP TRIGGER mockmessageevent_immutable ON customers_mockmessageevent; DROP TRIGGER mockmessagesubmission_immutable ON customers_mockmessagesubmission; DROP FUNCTION railet_mock_message_immutable();')


class Migration(migrations.Migration):
    dependencies = [('customers', '0008_mockmessagesubmission_mockmessageevent_and_more')]
    operations = [migrations.RunPython(forwards, backwards)]

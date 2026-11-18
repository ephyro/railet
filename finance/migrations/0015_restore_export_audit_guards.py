# SPDX-License-Identifier: MPL-2.0
from django.db import migrations


def restore_guards(apps, schema_editor):
    # SQLite table rebuilds in later AlterField operations discard table triggers.
    # Reinstall in place: existing audit rows must not be copied or changed.
    if schema_editor.connection.vendor == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            schema_editor.execute(
                f"CREATE TRIGGER IF NOT EXISTS demo_account_export_{operation.lower()} "
                f"BEFORE {operation} ON finance_demoaccountexport "
                "BEGIN SELECT RAISE(ABORT, 'Export audit is immutable'); END"
            )


class Migration(migrations.Migration):
    dependencies = [('finance', '0014_restore_context_guards')]
    # Reversing this repair must not deliberately remove an integrity guard.
    operations = [migrations.RunPython(restore_guards, migrations.RunPython.noop)]

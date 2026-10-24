# SPDX-License-Identifier: MPL-2.0
import uuid

from django.db import migrations, models


def assign_existing_keys(apps, schema_editor):
    DraftDeal = apps.get_model("deals", "DraftDeal")
    drafts = DraftDeal.objects.using(schema_editor.connection.alias)
    for pk in drafts.filter(creation_key__isnull=True).values_list("pk", flat=True).iterator():
        drafts.filter(pk=pk).update(creation_key=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [("deals", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="draftdeal",
            name="creation_key",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(assign_existing_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="draftdeal",
            name="creation_key",
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
        migrations.AddConstraint(
            model_name="draftdeal",
            constraint=models.UniqueConstraint(fields=["dealership", "creation_key"], name="draft_creation_key_per_dealer"),
        ),
    ]

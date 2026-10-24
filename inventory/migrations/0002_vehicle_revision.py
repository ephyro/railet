# SPDX-License-Identifier: MPL-2.0
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="vehicle",
            name="revision",
            field=models.PositiveIntegerField(default=1, editable=False),
        ),
    ]

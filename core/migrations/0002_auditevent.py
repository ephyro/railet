# SPDX-License-Identifier: MPL-2.0
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial"), ("inventory", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="AuditEvent", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("action", models.CharField(max_length=40)), ("changes", models.JSONField()), ("created_at", models.DateTimeField(auto_now_add=True)), ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)), ("dealership", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.dealership")), ("vehicle", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="inventory.vehicle"))], options={"ordering": ["-created_at", "-pk"]})]

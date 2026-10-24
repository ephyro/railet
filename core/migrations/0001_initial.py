# SPDX-License-Identifier: MPL-2.0
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="Dealership", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("name", models.CharField(max_length=180))]),
        migrations.CreateModel(name="Membership", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("role", models.CharField(choices=[("owner", "Owner"), ("staff", "Inventory staff"), ("viewer", "Read only")], default="viewer", max_length=12)), ("dealership", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.dealership")), ("user", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL))]),
    ]

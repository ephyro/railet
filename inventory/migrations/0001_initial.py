# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
class Migration(migrations.Migration):
    initial = True
    dependencies = [("core", "0001_initial")]
    operations = [migrations.CreateModel(name="Vehicle", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("stock_number", models.CharField(max_length=30)),
        ("vin", models.CharField(blank=True, help_text="Record as shown on ownership documents; historical VIN formats are supported.", max_length=30)),
        ("year", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1886)])),
        ("make", models.CharField(max_length=60)), ("model", models.CharField(max_length=80)),
        ("title_brand", models.CharField(choices=[("unknown", "Not verified"), ("unbranded", "No brand recorded"), ("rebuilt", "Rebuilt"), ("salvage", "Salvage"), ("flood", "Flood"), ("other", "Other — review notes")], default="unknown", max_length=15)),
        ("title_received", models.BooleanField(default=False)),
        ("status", models.CharField(choices=[("acquired", "Acquired"), ("recon", "In reconditioning"), ("available", "Available"), ("sold", "Sold")], default="acquired", max_length=15)),
        ("acquisition_cost", models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
        ("recon_cost", models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
        ("notes", models.TextField(blank=True, help_text="Vehicle notes only. Do not enter customer or financial account information.")),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("dealership", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.dealership")),
    ], options={"ordering": ["-updated_at", "-pk"], "constraints": [models.UniqueConstraint(fields=("dealership", "stock_number"), name="unique_dealer_stock"), models.CheckConstraint(condition=models.Q(acquisition_cost__gte=0, recon_cost__gte=0), name="vehicle_costs_nonnegative")]})]

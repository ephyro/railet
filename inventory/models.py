# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models
from django.conf import settings
from django.utils.functional import cached_property
from core.storage import PrivateMediaStorage
from .identity import OdometerUnit, OdometerStatus, validate_odometer

class Vehicle(models.Model):
    class Brand(models.TextChoices):
        UNKNOWN = "unknown", "Not verified"
        UNBRANDED = "unbranded", "No brand recorded"
        REBUILT = "rebuilt", "Rebuilt"
        SALVAGE = "salvage", "Salvage"
        FLOOD = "flood", "Flood"
        OTHER = "other", "Other — review notes"
    class Status(models.TextChoices):
        ACQUIRED = "acquired", "Acquired"
        RECON = "recon", "In reconditioning"
        AVAILABLE = "available", "Available"
        SOLD = "sold", "Sold"
    dealership = models.ForeignKey("core.Dealership", on_delete=models.PROTECT)
    stock_number = models.CharField(max_length=30)
    vin = models.CharField(max_length=30, blank=True, help_text="Record as shown on ownership documents; historical VIN formats are supported.")
    year = models.PositiveSmallIntegerField(validators=[MinValueValidator(1886)])
    make = models.CharField(max_length=60)
    model = models.CharField(max_length=80)
    title_brand = models.CharField(max_length=15, choices=Brand.choices, default=Brand.UNKNOWN)
    title_received = models.BooleanField(default=False)
    odometer_reading = models.PositiveIntegerField(null=True, blank=True)
    odometer_unit = models.CharField(max_length=10, choices=OdometerUnit.choices, default=OdometerUnit.UNKNOWN)
    odometer_status = models.CharField(max_length=12, choices=OdometerStatus.choices, default=OdometerStatus.UNKNOWN)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ACQUIRED)
    acquired_on = models.DateField(null=True, blank=True, verbose_name="Acquisition date", help_text="Enter the date this stock was acquired, if known.")
    sold_on = models.DateField(null=True, blank=True, verbose_name="Recorded sale date", help_text="Optional staff-entered historical date when status is Sold. Not verified proof of a sale.")
    acquisition_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0"))])
    recon_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0"))])
    asking_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))], help_text="Optional asking price. Leave blank until a price is chosen.")
    notes = models.TextField(blank=True, help_text="Vehicle notes only. Do not enter customer or financial account information.")
    updated_at = models.DateTimeField(auto_now=True)
    revision = models.PositiveIntegerField(default=1, editable=False)
    class Meta:
        ordering = ["-updated_at", "-pk"]
        constraints = [models.UniqueConstraint(fields=["dealership", "stock_number"], name="unique_dealer_stock"), models.CheckConstraint(condition=models.Q(acquisition_cost__gte=0, recon_cost__gte=0), name="vehicle_costs_nonnegative"), models.CheckConstraint(condition=models.Q(asking_price__isnull=True) | models.Q(asking_price__gte=0), name="vehicle_asking_nonnegative")]
    @property
    def total_cost(self):
        return self.acquisition_cost + self.recon_cost + self.itemized_cost
    @property
    def asking_less_cost(self):
        return None if self.asking_price is None else self.asking_price - self.total_cost

    @property
    def itemized_cost(self):
        if hasattr(self, "registered_cost_cents"):
            return Decimal(self.registered_cost_cents) / 100
        from .reconditioning import with_cost_totals
        cents = with_cost_totals(type(self).objects.filter(pk=self.pk)).values_list("registered_cost_cents", flat=True).first() if self.pk else 0
        return Decimal(cents or 0) / 100

    def __str__(self):
        return f"{self.year} {self.make} {self.model}"

    def clean(self):
        super().clean()
        validate_odometer(self)

    @cached_property
    def cover_photo(self):
        if hasattr(self, "visible_photos"):
            return self.visible_photos[0] if self.visible_photos else None
        return self.photos.filter(archived_at__isnull=True).order_by("-is_primary", "pk").first()


class VehiclePhoto(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="photos")
    image = models.FileField(storage=PrivateMediaStorage(), upload_to="vehicles/")
    thumbnail = models.FileField(storage=PrivateMediaStorage(), upload_to="vehicles/")
    is_primary = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-is_primary", "pk"]
        constraints = [models.UniqueConstraint(fields=["vehicle"], condition=models.Q(is_primary=True, archived_at__isnull=True), name="one_active_vehicle_cover")]

# Keep inventory's work/cost records explicit without creating another service.
from .reconditioning_models import VehicleVendor, VehicleVendorEvent, ReconTask, VehicleCostEntry  # noqa: E402,F401

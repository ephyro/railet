# SPDX-License-Identifier: MPL-2.0
"""Internal work tracking and synthetic cost-control pairs, not accounts payable."""
import uuid
from django.conf import settings
from django.db import models


class VehicleVendor(models.Model):
    dealership = models.ForeignKey('core.Dealership', on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    normalized_name = models.CharField(max_length=120, editable=False)
    contact_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=240, blank=True)
    notes = models.TextField(max_length=1000, blank=True)
    revision = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'pk']
        constraints = [models.UniqueConstraint(fields=['dealership', 'normalized_name'], name='unique_vehicle_vendor_name')]

    def __str__(self):
        return self.name


class VehicleVendorEvent(models.Model):
    vendor = models.ForeignKey(VehicleVendor, on_delete=models.PROTECT, related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=24)
    changes = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']


class ReconTask(models.Model):
    class Status(models.TextChoices):
        TODO = 'todo', 'To do'
        IN_PROGRESS = 'in_progress', 'In progress'
        DONE = 'done', 'Done'
    vehicle = models.ForeignKey('inventory.Vehicle', on_delete=models.PROTECT, related_name='recon_tasks')
    title = models.CharField(max_length=160)
    detail = models.TextField(max_length=2000, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.TODO)
    vendor = models.ForeignKey(VehicleVendor, on_delete=models.PROTECT, null=True, blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='recon_tasks_assigned')
    due_on = models.DateField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)
    creation_key = models.UUIDField(default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['pk']
        constraints = [
            models.UniqueConstraint(fields=['vehicle', 'creation_key'], name='unique_vehicle_recon_key'),
            models.CheckConstraint(condition=models.Q(status__in=['todo', 'in_progress', 'done']), name='recon_status_known'),
        ]

    def __str__(self):
        return self.title


class VehicleCostEntry(models.Model):
    class Category(models.TextChoices):
        PURCHASE = 'purchase', 'Additional purchase cost'
        AUCTION = 'auction', 'Auction fee'
        TRANSPORT = 'transport', 'Transport'
        REPAIR = 'repair', 'Repair / labor'
        PARTS = 'parts', 'Parts'
        DETAIL = 'detail', 'Detailing'
        OTHER = 'other', 'Other'
    vehicle = models.ForeignKey('inventory.Vehicle', on_delete=models.PROTECT, related_name='cost_entries')
    kind = models.CharField(max_length=8, choices=[('cost', 'Cost'), ('reversal', 'Cost reversal')])
    category = models.CharField(max_length=12, choices=Category.choices)
    description = models.CharField(max_length=180)
    amount_cents = models.BigIntegerField()
    debit = models.CharField(max_length=20, default='vehicle_cost')
    credit = models.CharField(max_length=20, default='cost_offset')
    vendor = models.ForeignKey(VehicleVendor, on_delete=models.PROTECT, null=True, blank=True)
    vendor_name = models.CharField(max_length=120, blank=True)
    task = models.ForeignKey(ReconTask, on_delete=models.PROTECT, null=True, blank=True)
    reverses = models.OneToOneField('self', on_delete=models.PROTECT, null=True, blank=True, related_name='correction')
    reason = models.CharField(max_length=300, blank=True)
    effective_on = models.DateField()
    request_key = models.UUIDField(default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    entered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-entered_at', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['vehicle', 'request_key'], name='unique_vehicle_cost_key'),
            models.CheckConstraint(condition=models.Q(amount_cents__gt=0, amount_cents__lte=999999999999), name='vehicle_cost_positive_bounded'),
            models.CheckConstraint(condition=models.Q(category__in=['purchase', 'auction', 'transport', 'repair', 'parts', 'detail', 'other']), name='vehicle_cost_category_known'),
            models.CheckConstraint(condition=(
                models.Q(kind='cost', debit='vehicle_cost', credit='cost_offset', reverses__isnull=True)
                | models.Q(kind='reversal', debit='cost_offset', credit='vehicle_cost', reverses__isnull=False)
            ), name='vehicle_cost_balanced_pair'),
        ]

    @property
    def amount(self):
        from decimal import Decimal
        return Decimal(self.amount_cents) / 100

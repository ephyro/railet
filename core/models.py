# SPDX-License-Identifier: MPL-2.0
from django.conf import settings
from django.db import models

class Dealership(models.Model):
    name = models.CharField(max_length=180)
    def __str__(self):
        return self.name

class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        STAFF = "staff", "Inventory staff"
        VIEWER = "viewer", "Read only"
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    dealership = models.ForeignKey(Dealership, on_delete=models.PROTECT)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.VIEWER)
    @property
    def can_manage_inventory(self):
        return self.role in (self.Role.OWNER, self.Role.STAFF)

class AuditEvent(models.Model):
    """Inventory audit history; database guards reject mutation and invalid ownership."""
    dealership = models.ForeignKey(Dealership, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    vehicle = models.ForeignKey("inventory.Vehicle", on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    changes = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at", "-pk"]


class SavedView(models.Model):
    dealership = models.ForeignKey(Dealership, on_delete=models.PROTECT)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    resource = models.CharField(max_length=30)
    name = models.CharField(max_length=60)
    parameters = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [models.UniqueConstraint(fields=["dealership", "owner", "resource", "name"], name="unique_personal_saved_view")]


class DealershipExportEvent(models.Model):
    """Metadata-only record that an owner package response was prepared."""
    dealership = models.ForeignKey(Dealership, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    format_version = models.CharField(max_length=80)
    sha256 = models.CharField(max_length=64)
    byte_size = models.PositiveBigIntegerField()


class SyntheticMFAFactor(models.Model):
    """Invented identities only; never connected to application users."""
    dealership_ref = models.CharField(max_length=90)
    user_ref = models.CharField(max_length=90)
    factor_ref = models.CharField(max_length=90)
    secret_envelope = models.JSONField()
    last_step = models.BigIntegerField(default=-1)
    failure_count = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['dealership_ref', 'user_ref', 'factor_ref'], name='synthetic_mfa_factor_unique')]


class SyntheticMFAEvent(models.Model):
    """Minimal append-only synthetic verification history."""
    factor = models.ForeignKey(SyntheticMFAFactor, on_delete=models.PROTECT)
    outcome = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True)

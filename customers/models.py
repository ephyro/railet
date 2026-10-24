# SPDX-License-Identifier: MPL-2.0
from django.conf import settings
from django.db import models

def phone_key(value):
    digits = "".join(c for c in value if c.isdigit())
    return digits[1:] if len(digits) == 11 and digits.startswith("1") else digits

class Customer(models.Model):
    dealership = models.ForeignKey("core.Dealership", on_delete=models.PROTECT)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    phone_normalized = models.CharField(max_length=40, blank=True, editable=False, db_index=True)
    email_normalized = models.CharField(max_length=254, blank=True, editable=False, db_index=True)
    revision = models.PositiveIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["last_name", "first_name", "pk"]
    def save(self, *args, **kwargs):
        self.phone_normalized = phone_key(self.phone)
        self.email_normalized = self.email.strip().casefold()
        super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class CustomerEvent(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    changes = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at", "-pk"]

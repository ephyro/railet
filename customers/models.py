# SPDX-License-Identifier: MPL-2.0
from django.conf import settings
from django.db import models

def phone_key(value):
    digits = "".join(c for c in value if c.isdigit())
    return digits[1:] if len(digits) == 11 and digits.startswith("1") else digits

ADDRESS_FIELDS = ('address_line1', 'address_line2', 'city', 'region', 'postal_code', 'country')


class Customer(models.Model):
    class LeadStage(models.TextChoices):
        UNSPECIFIED = "", "Not set"
        NEW = "new", "New inquiry"
        CONTACTED = "contacted", "Contacted"
        VISIT = "visit", "Visit / appointment"
        WORKING_DEAL = "working_deal", "Working a deal"
        INACTIVE = "inactive", "Inactive / not pursuing"
    dealership = models.ForeignKey("core.Dealership", on_delete=models.PROTECT)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    lead_stage = models.CharField(
        max_length=20,
        choices=LeadStage.choices,
        default=LeadStage.UNSPECIFIED,
        blank=True,
        help_text="Internal sales progress only. Does not record communication consent, a credit decision, or a completed sale.",
    )
    address_line1 = models.CharField(max_length=160, blank=True)
    address_line2 = models.CharField(max_length=160, blank=True)
    city = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=24, blank=True)
    country = models.CharField(max_length=100, blank=True)
    phone_normalized = models.CharField(max_length=40, blank=True, editable=False, db_index=True)
    email_normalized = models.CharField(max_length=254, blank=True, editable=False, db_index=True)
    revision = models.PositiveIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["last_name", "first_name", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(lead_stage__in=("", "new", "contacted", "visit", "working_deal", "inactive")),
                name="customer_lead_stage_known",
            ),
        ]
    def save(self, *args, **kwargs):
        self.phone_normalized = phone_key(self.phone)
        self.email_normalized = self.email.strip().casefold()
        super().save(*args, **kwargs)
    @property
    def address_lines(self):
        locality = ', '.join(value for value in (self.city, self.region) if value)
        if self.postal_code:
            locality = ' '.join(value for value in (locality, self.postal_code) if value)
        return tuple(value for value in (self.address_line1, self.address_line2, locality, self.country) if value)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class CustomerEvent(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    changes = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at", "-pk"]


class CustomerActivity(models.Model):
    """Manual customer follow-up or conversation, scoped through the customer."""
    class Kind(models.TextChoices):
        NOTE = 'note', 'Conversation note'
        FOLLOW_UP = 'follow_up', 'Follow-up'
        APPOINTMENT = 'appointment', 'Appointment'
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='activities')
    kind = models.CharField(max_length=12, choices=Kind.choices)
    detail = models.TextField(max_length=2000)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='customer_activities_created')
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='customer_activities_completed')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='customer_activities_assigned')
    revision = models.PositiveIntegerField(default=1)
    creation_key = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['customer', 'creation_key'], name='unique_customer_activity_key'),
            models.CheckConstraint(condition=models.Q(kind__in=['note', 'follow_up', 'appointment']), name='customer_activity_kind_known'),
            models.CheckConstraint(condition=models.Q(completed_at__isnull=True, completed_by__isnull=True) | models.Q(completed_at__isnull=False, completed_by__isnull=False), name='customer_activity_completion_pair')]


class CustomerExportEvent(models.Model):
    """Records an export response prepared; no customer content is stored here."""
    dealership = models.ForeignKey('core.Dealership', on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    format_version = models.CharField(max_length=80)
    sha256 = models.CharField(max_length=64)
    byte_size = models.PositiveBigIntegerField()


class MockMessageSubmission(models.Model):
    """Offline rehearsal with fixed labels; not a customer communication."""
    dealership = models.ForeignKey('core.Dealership', on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    submission_id = models.UUIDField()
    recipient_label = models.CharField(max_length=24, choices=[('mock-recipient-alpha', 'Mock alpha'), ('mock-recipient-beta', 'Mock beta')])
    scenario = models.CharField(max_length=20, choices=[('mock-follow-up', 'Mock follow-up'), ('mock-appointment', 'Mock appointment')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['dealership', 'submission_id'], name='unique_mock_submission_dealer'),
            models.CheckConstraint(condition=models.Q(recipient_label__in=['mock-recipient-alpha', 'mock-recipient-beta']), name='mock_message_recipient_known'),
            models.CheckConstraint(condition=models.Q(scenario__in=['mock-follow-up', 'mock-appointment']), name='mock_message_scenario_known'),
        ]


class MockMessageEvent(models.Model):
    """Append-only locally invented observation, not a provider callback."""
    submission = models.ForeignKey(MockMessageSubmission, on_delete=models.PROTECT, related_name='events')
    event_id = models.UUIDField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    label = models.CharField(max_length=20, choices=[('mock-accepted', 'Mock accepted'), ('mock-delivered', 'Mock delivered'), ('mock-failed', 'Mock failed')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [
            models.UniqueConstraint(fields=['submission', 'event_id'], name='unique_mock_message_event'),
            models.CheckConstraint(condition=models.Q(label__in=['mock-accepted', 'mock-delivered', 'mock-failed']), name='mock_message_event_known'),
        ]

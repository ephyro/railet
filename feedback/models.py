# SPDX-License-Identifier: MPL-2.0
import uuid
from django.conf import settings
from django.db import models


class FeedbackReport(models.Model):
    class Kind(models.TextChoices):
        BUG = 'bug', 'Something is not working'
        IDEA = 'idea', 'Suggest an improvement'
    class Area(models.TextChoices):
        GENERAL = 'general', 'General'
        INVENTORY = 'inventory', 'Inventory'
        CUSTOMERS = 'customers', 'Customers'
        DEALS = 'deals', 'Draft deals'
        DOCUMENTS = 'documents', 'Supporting files'
    dealership = models.ForeignKey('core.Dealership', on_delete=models.PROTECT)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    submission_key = models.UUIDField(default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    area = models.CharField(max_length=15, choices=Area.choices)
    subject = models.CharField(max_length=120)
    expected = models.TextField(max_length=2000)
    actual = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['dealership', 'author', 'submission_key'], name='unique_feedback_submission')]

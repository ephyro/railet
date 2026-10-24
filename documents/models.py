# SPDX-License-Identifier: MPL-2.0
import uuid

from django.conf import settings
from django.db import models

from core.storage import PrivateMediaStorage


class DealFile(models.Model):
    deal = models.ForeignKey(
        "deals.DraftDeal",
        on_delete=models.PROTECT,
        related_name="supporting_files",
    )
    title = models.CharField(max_length=120)
    blob = models.FileField(
        storage=PrivateMediaStorage(),
        upload_to="deal-files/",
    )
    sha256 = models.CharField(max_length=64)
    byte_size = models.PositiveIntegerField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(blank=True, null=True)
    upload_key = models.UUIDField(default=uuid.uuid4, editable=False)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["deal", "upload_key"],
                name="unique_deal_file_upload_key",
            ),
        ]

    def __str__(self):
        return self.title


class DealFileEvent(models.Model):
    class Action(models.TextChoices):
        UPLOAD = "upload", "Upload"
        ARCHIVE = "archive", "Archive"
        RESTORE = "restore", "Restore"
        DOWNLOAD = "download", "Download"

    file = models.ForeignKey(DealFile, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=12, choices=Action.choices)
    reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]


# SPDX-License-Identifier: MPL-2.0
"""Private supporting-file operations for saved draft deals."""
import hashlib
import uuid

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from deals.models import DraftDeal

from .models import DealFile, DealFileEvent


MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_DEAL_FILES = 100
MAX_DEAL_BYTES = 100 * 1024 * 1024
MAX_TITLE_LENGTH = 120
MAX_REASON_LENGTH = 300


class FileWorkflowError(Exception):
    """Actionable error for a supporting-file request."""


class InvalidPdfFile(FileWorkflowError):
    pass


class UploadKeyConflict(FileWorkflowError):
    pass


class DealFileQuotaExceeded(FileWorkflowError):
    pass


def validate_pdf_bytes(data):
    """Apply minimal format and size checks; this does not validate or sanitize PDFs."""
    if not data:
        raise InvalidPdfFile("The selected file is empty. Choose a PDF with content.")
    if len(data) > MAX_FILE_BYTES:
        raise InvalidPdfFile("Choose a PDF no larger than 8 MiB.")
    if not data.startswith(b"%PDF-"):
        raise InvalidPdfFile("The file does not begin with a PDF signature. Choose a PDF file.")
    if b"%%EOF" not in data[-2048:]:
        raise InvalidPdfFile("The file is missing a PDF end marker near the end. Choose another PDF.")
    return len(data)


def _locked_scoped_deal(*, deal_id, dealership_id):
    return DraftDeal.objects.select_for_update().get(
        pk=deal_id,
        dealership_id=dealership_id,
    )


def _delete_new_blobs(storage, names):
    errors = []
    for name in reversed(names):
        try:
            storage.delete(name)
        except Exception as error:  # Cleanup failure needs a clear failure, not a false success.
            errors.append(error)
    if errors:
        raise FileWorkflowError(
            "The file could not be saved and private storage cleanup also failed. Contact the system administrator."
        ) from errors[0]


def upload_deal_file(*, deal_id, dealership_id, actor, title, upload_key, pdf_bytes):
    """Store one immutable PDF and upload event, with cleanup around DB commit."""
    byte_size = validate_pdf_bytes(pdf_bytes)
    if not title or len(title) > MAX_TITLE_LENGTH:
        raise FileWorkflowError("Enter a file title of 120 characters or fewer.")
    if not isinstance(upload_key, uuid.UUID):
        raise FileWorkflowError("Refresh the Files page and try the upload again.")

    digest = hashlib.sha256(pdf_bytes).hexdigest()
    storage = DealFile._meta.get_field("blob").storage
    written_names = []
    try:
        # durable=True rejects an outer transaction so cleanup also covers commit failure.
        with transaction.atomic(durable=True):
            deal = _locked_scoped_deal(deal_id=deal_id, dealership_id=dealership_id)
            existing = DealFile.objects.select_for_update().filter(
                deal=deal,
                upload_key=upload_key,
            ).first()
            if existing:
                if (
                    existing.sha256 == digest
                    and existing.title == title
                    and existing.byte_size == byte_size
                ):
                    return existing, False
                raise UploadKeyConflict(
                    "This submission key is already linked to a different file or title. No new file was saved. Check the saved files, then start a fresh upload if you intend to add a separate item."
                )

            retained = DealFile.objects.filter(deal=deal)
            retained_count = retained.count()
            retained_bytes = retained.aggregate(total=Sum("byte_size"))["total"] or 0
            if retained_count >= MAX_DEAL_FILES:
                raise DealFileQuotaExceeded(
                    "This draft already has 100 retained files, including archived files. Archive does not free file space."
                )
            if retained_bytes + byte_size > MAX_DEAL_BYTES:
                raise DealFileQuotaExceeded(
                    "This draft's retained files would exceed 100 MiB, including archived files. Archive does not free file space."
                )

            requested_name = f"deal-files/{uuid.uuid4()}.pdf"
            stored_name = storage.save(requested_name, ContentFile(pdf_bytes))
            written_names.append(stored_name)
            deal_file = DealFile.objects.create(
                deal=deal,
                title=title,
                blob=stored_name,
                sha256=digest,
                byte_size=byte_size,
                created_by=actor,
                upload_key=upload_key,
            )
            DealFileEvent.objects.create(
                file=deal_file,
                actor=actor,
                action=DealFileEvent.Action.UPLOAD,
            )
        return deal_file, True
    except BaseException:
        try:
            _delete_new_blobs(storage, written_names)
        except FileWorkflowError:
            raise
        raise


def change_deal_file_state(
    *, deal_id, dealership_id, file_id, actor, action, reason=""
):
    """Archive or restore a file and append an event while holding its deal lock."""
    if action not in (DealFileEvent.Action.ARCHIVE, DealFileEvent.Action.RESTORE):
        raise FileWorkflowError("Choose Archive or Restore for this file.")
    reason = (reason or "").strip()
    if len(reason) > MAX_REASON_LENGTH:
        raise FileWorkflowError("Keep the reason to 300 characters or fewer.")
    if action == DealFileEvent.Action.ARCHIVE and not reason:
        raise FileWorkflowError("Enter a reason to archive this file.")

    with transaction.atomic():
        deal = _locked_scoped_deal(deal_id=deal_id, dealership_id=dealership_id)
        deal_file = DealFile.objects.select_for_update().get(pk=file_id, deal=deal)
        is_archived = deal_file.archived_at is not None
        if action == DealFileEvent.Action.ARCHIVE:
            if is_archived:
                return deal_file, False
            deal_file.archived_at = timezone.now()
            event_action = DealFileEvent.Action.ARCHIVE
            event_reason = reason
        else:
            if not is_archived:
                return deal_file, False
            deal_file.archived_at = None
            event_action = DealFileEvent.Action.RESTORE
            event_reason = reason

        deal_file.save(update_fields=["archived_at"])
        DealFileEvent.objects.create(
            file=deal_file,
            actor=actor,
            action=event_action,
            reason=event_reason,
        )
        return deal_file, True

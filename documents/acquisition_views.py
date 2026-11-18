# SPDX-License-Identifier: MPL-2.0
"""Private synthetic vehicle acquisition attachments; never verified proof of ownership or sale readiness."""
import hashlib
import uuid
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Prefetch, Sum
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from core.access import authorized_private_read, context, member_view, require_editor
from inventory.models import Vehicle
from .forms import DealFileActionForm, SupportingFileUploadForm
from .models import VehicleAcquisitionFile, VehicleAcquisitionFileEvent
from .services import (
    MAX_FILE_BYTES,
    MAX_REASON_LENGTH,
    MAX_TITLE_LENGTH,
    FileWorkflowError,
    UploadKeyConflict,
    _delete_new_blobs,
    _lock_dealership,
    _require_locked_editor,
    validate_pdf_bytes,
)
from .views import _check_private_reference, _set_download_headers, private_no_store

MAX_VEHICLE_ACQUISITION_FILES = 100
MAX_VEHICLE_ACQUISITION_BYTES = 100 * 1024 * 1024


class AcquisitionFileUploadForm(SupportingFileUploadForm):
    description = forms.CharField(
        max_length=300,
        required=False,
        strip=True,
        label="Description (optional)",
        help_text="Describe this synthetic attachment (for example, auction bill of sale rehearsal). Does not verify ownership or title.",
    )
    field_order = ["title", "description", "pdf_file", "upload_key"]


def upload_acquisition_file(*, vehicle_id, dealership_id, actor, title, description="", upload_key, pdf_bytes):
    if not getattr(settings, "DEAL_FILES_DEMO_ENABLED", False):
        raise PermissionDenied("Synthetic vehicle acquisition files are disabled.")
    byte_size = validate_pdf_bytes(pdf_bytes)
    title = (title or "").strip()
    description = (description or "").strip()
    if not title or len(title) > MAX_TITLE_LENGTH:
        raise FileWorkflowError("Enter a file title of 120 characters or fewer.")
    if len(description) > 300:
        raise FileWorkflowError("Keep the description to 300 characters or fewer.")
    if not isinstance(upload_key, uuid.UUID):
        raise FileWorkflowError("Refresh the page and try the upload again.")

    digest = hashlib.sha256(pdf_bytes).hexdigest()
    storage = VehicleAcquisitionFile._meta.get_field("blob").storage
    written = []
    try:
        with transaction.atomic(durable=True):
            _lock_dealership(dealership_id)
            vehicle = Vehicle.objects.select_for_update().get(pk=vehicle_id, dealership_id=dealership_id)
            _require_locked_editor(actor, dealership_id)
            existing = VehicleAcquisitionFile.objects.select_for_update().filter(
                vehicle=vehicle, upload_key=upload_key
            ).first()
            if existing:
                if (existing.created_by_id, existing.sha256, existing.title, existing.description, existing.byte_size) == (
                    actor.pk, digest, title, description, byte_size
                ):
                    return existing, False
                raise UploadKeyConflict(
                    "This submission key is already linked to a different file, title, description, or uploader. Start a fresh upload."
                )

            retained = VehicleAcquisitionFile.objects.filter(vehicle=vehicle)
            if retained.count() >= MAX_VEHICLE_ACQUISITION_FILES or (
                (retained.aggregate(total=Sum("byte_size"))["total"] or 0) + byte_size > MAX_VEHICLE_ACQUISITION_BYTES
            ):
                raise FileWorkflowError("This vehicle has reached its retained acquisition file storage limit.")

            name = storage.save(f"vehicle-acquisition/{uuid.uuid4()}.pdf", ContentFile(pdf_bytes))
            written.append(name)
            record = VehicleAcquisitionFile.objects.create(
                vehicle=vehicle,
                title=title,
                description=description,
                blob=name,
                sha256=digest,
                byte_size=byte_size,
                upload_key=upload_key,
                created_by=actor,
            )
            VehicleAcquisitionFileEvent.objects.create(
                file=record, actor=actor, action=VehicleAcquisitionFileEvent.Action.UPLOAD
            )
        return record, True
    except BaseException:
        _delete_new_blobs(storage, written)
        raise


def change_acquisition_file_state(*, vehicle_id, dealership_id, file_id, actor, action, reason=""):
    if not getattr(settings, "DEAL_FILES_DEMO_ENABLED", False):
        raise PermissionDenied("Synthetic vehicle acquisition files are disabled.")
    if action not in (VehicleAcquisitionFileEvent.Action.ARCHIVE, VehicleAcquisitionFileEvent.Action.RESTORE):
        raise FileWorkflowError("Choose Archive or Restore for this file.")
    reason = (reason or "").strip()
    if len(reason) > MAX_REASON_LENGTH:
        raise FileWorkflowError("Keep the reason to 300 characters or fewer.")
    if action == VehicleAcquisitionFileEvent.Action.ARCHIVE and not reason:
        raise FileWorkflowError("Enter a reason to archive this file.")

    with transaction.atomic():
        _lock_dealership(dealership_id)
        vehicle = Vehicle.objects.select_for_update().get(pk=vehicle_id, dealership_id=dealership_id)
        _require_locked_editor(actor, dealership_id)
        record = VehicleAcquisitionFile.objects.select_for_update().get(pk=file_id, vehicle=vehicle)
        is_archived = record.archived_at is not None
        if action == VehicleAcquisitionFileEvent.Action.ARCHIVE:
            if is_archived:
                return record, False
            record.archived_at = timezone.now()
            event_action = VehicleAcquisitionFileEvent.Action.ARCHIVE
        else:
            if not is_archived:
                return record, False
            record.archived_at = None
            event_action = VehicleAcquisitionFileEvent.Action.RESTORE
        record.save(update_fields=["archived_at"])
        VehicleAcquisitionFileEvent.objects.create(
            file=record, actor=actor, action=event_action, reason=reason
        )
        return record, True


def _rows(files, *, action_file_id=None, action=None, bound_form=None):
    rows = []
    for item in files:
        archive_form = DealFileActionForm(
            prefix=f"file-{item.pk}-archive",
            initial={"action": VehicleAcquisitionFileEvent.Action.ARCHIVE},
            expected_action=VehicleAcquisitionFileEvent.Action.ARCHIVE,
        )
        restore_form = DealFileActionForm(
            prefix=f"file-{item.pk}-restore",
            initial={"action": VehicleAcquisitionFileEvent.Action.RESTORE},
            expected_action=VehicleAcquisitionFileEvent.Action.RESTORE,
        )
        if bound_form is not None and item.pk == action_file_id:
            if action == VehicleAcquisitionFileEvent.Action.ARCHIVE:
                archive_form = bound_form
            elif action == VehicleAcquisitionFileEvent.Action.RESTORE:
                restore_form = bound_form
        archive_events = getattr(item, "archive_events", [])
        rows.append({
            "file": item,
            "archive_form": archive_form,
            "restore_form": restore_form,
            "archive_event": archive_events[0] if archive_events else None,
        })
    return rows


def _render_page(request, vehicle, *, upload_form=None, action_form=None, action_file_id=None, action=None, status=200):
    qs = vehicle.acquisition_files.select_related("created_by")
    if not request.member.can_manage_inventory:
        qs = qs.filter(archived_at__isnull=True)
    files = list(
        qs.prefetch_related(
            Prefetch(
                "events",
                queryset=VehicleAcquisitionFileEvent.objects.filter(
                    action=VehicleAcquisitionFileEvent.Action.ARCHIVE
                ).order_by("-created_at", "-pk"),
                to_attr="archive_events",
            )
        )
    )
    active = [f for f in files if f.archived_at is None]
    archived = [f for f in files if f.archived_at is not None]
    return render(
        request,
        "documents/vehicle_acquisition_files.html",
        context(
            request,
            vehicle=vehicle,
            upload_form=upload_form or AcquisitionFileUploadForm(),
            action_form=action_form,
            active_files=_rows(active, action_file_id=action_file_id, action=action, bound_form=action_form),
            archived_files=_rows(archived, action_file_id=action_file_id, action=action, bound_form=action_form)
            if request.member.can_manage_inventory
            else [],
        ),
        status=status,
    )


@private_no_store
@member_view
def acquisition_files(request, pk):
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])
    if request.method == "POST":
        require_editor(request)
    vehicle = get_object_or_404(Vehicle, pk=pk, dealership_id=request.member.dealership_id)
    if request.method == "GET":
        return _render_page(request, vehicle)

    form = AcquisitionFileUploadForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            _, created = upload_acquisition_file(
                vehicle_id=vehicle.pk,
                dealership_id=request.member.dealership_id,
                actor=request.user,
                title=form.cleaned_data["title"],
                description=form.cleaned_data["description"],
                upload_key=form.cleaned_data["upload_key"],
                pdf_bytes=form.cleaned_data["pdf_file"],
            )
        except FileWorkflowError as error:
            form.add_error(None, str(error))
            if isinstance(error, UploadKeyConflict):
                form.upload_key_conflict = True
        else:
            if created:
                messages.success(request, "Acquisition attachment saved. It is unverified and does not establish ownership.")
            else:
                messages.info(request, "This upload was already saved. Its current archive state was kept.")
            return redirect("vehicle_acquisition_files", pk=vehicle.pk)
    return _render_page(request, vehicle, upload_form=form)


@private_no_store
@member_view
def acquisition_file_action(request, pk, file_pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    require_editor(request)
    vehicle = get_object_or_404(Vehicle, pk=pk, dealership_id=request.member.dealership_id)
    record = get_object_or_404(VehicleAcquisitionFile, pk=file_pk, vehicle=vehicle)

    prefix_and_action = None
    for act in (VehicleAcquisitionFileEvent.Action.ARCHIVE, VehicleAcquisitionFileEvent.Action.RESTORE):
        prefix = f"file-{record.pk}-{act}"
        if f"{prefix}-action" in request.POST:
            prefix_and_action = (prefix, act)
            break
    if prefix_and_action is None:
        form = DealFileActionForm(
            request.POST,
            prefix=f"file-{record.pk}-archive",
            expected_action=VehicleAcquisitionFileEvent.Action.ARCHIVE,
        )
        form.add_error(None, "Choose Archive or Restore for this file.")
        return _render_page(
            request, vehicle, action_form=form, action_file_id=record.pk, action=VehicleAcquisitionFileEvent.Action.ARCHIVE
        )

    prefix, expected_action = prefix_and_action
    form = DealFileActionForm(request.POST, prefix=prefix, expected_action=expected_action)
    if not form.is_valid():
        return _render_page(request, vehicle, action_form=form, action_file_id=record.pk, action=expected_action)

    try:
        _, changed = change_acquisition_file_state(
            vehicle_id=vehicle.pk,
            dealership_id=request.member.dealership_id,
            file_id=record.pk,
            actor=request.user,
            action=form.cleaned_data["action"],
            reason=form.cleaned_data["reason"],
        )
    except FileWorkflowError as error:
        form.add_error(None, str(error))
        return _render_page(request, vehicle, action_form=form, action_file_id=record.pk, action=expected_action)

    if changed and expected_action == VehicleAcquisitionFileEvent.Action.ARCHIVE:
        messages.success(request, "Acquisition file archived. Its bytes and history are retained.")
    elif changed:
        messages.success(request, "Acquisition file restored.")
    else:
        messages.info(request, "This file was already in that state. No history entry was added.")
    return redirect("vehicle_acquisition_files", pk=vehicle.pk)


@private_no_store
@member_view
@authorized_private_read
def acquisition_file_download(request, pk, file_pk):
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    with transaction.atomic():
        vehicle = get_object_or_404(
            Vehicle.objects.select_for_update(), pk=pk, dealership_id=request.member.dealership_id
        )
        qs = VehicleAcquisitionFile.objects.filter(vehicle=vehicle)
        if not request.member.can_manage_inventory:
            qs = qs.filter(archived_at__isnull=True)
        record = get_object_or_404(qs, pk=file_pk)
        _check_private_reference(record, request.member.dealership_id)
        try:
            with record.blob.open("rb") as source:
                data = source.read(MAX_FILE_BYTES + 1)
        except OSError as error:
            raise Http404 from error
        if len(data) > MAX_FILE_BYTES or len(data) != record.byte_size or hashlib.sha256(data).hexdigest() != record.sha256:
            return HttpResponse(
                "Acquisition file integrity check failed. Contact your administrator.",
                status=409,
                content_type="text/plain",
            )
        if request.method == "GET":
            VehicleAcquisitionFileEvent.objects.create(
                file=record, actor=request.user, action=VehicleAcquisitionFileEvent.Action.DOWNLOAD
            )
    response = HttpResponse(data if request.method == "GET" else b"")
    return _set_download_headers(response, f"vehicle-acquisition-{record.pk}.pdf", record.byte_size)

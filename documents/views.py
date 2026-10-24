# SPDX-License-Identifier: MPL-2.0
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
    HttpResponseNotFound,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.access import context, member_view, require_editor
from deals.models import DraftDeal

from .forms import DealFileActionForm, SupportingFileUploadForm
from .models import DealFile, DealFileEvent
from .services import FileWorkflowError, UploadKeyConflict, change_deal_file_state, upload_deal_file


def private_no_store(view):
    """Apply private no-store headers even to auth redirects and scoped 404/403s."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not getattr(settings, "DEAL_FILES_DEMO_ENABLED", False):
            response = HttpResponseNotFound()
            response["Cache-Control"] = "private, no-store"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
            return response
        try:
            response = view(request, *args, **kwargs)
        except Http404:
            response = HttpResponseNotFound()
        except PermissionDenied:
            response = HttpResponseForbidden()
        response["Cache-Control"] = "private, no-store"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        return response

    return wrapped


def _gate_closed():
    if not getattr(settings, "DEAL_FILES_DEMO_ENABLED", False):
        raise Http404


def _scoped_deal(request, pk):
    return get_object_or_404(
        DraftDeal.objects.filter(dealership_id=request.member.dealership_id),
        pk=pk,
    )


def _files_for_member(request, deal):
    files = deal.supporting_files.all()
    if not request.member.can_manage_inventory:
        files = files.filter(archived_at__isnull=True)
    return files.prefetch_related(
        Prefetch(
            "events",
            queryset=DealFileEvent.objects.filter(
                action=DealFileEvent.Action.ARCHIVE
            ).order_by("-created_at", "-pk"),
            to_attr="archive_events",
        )
    )


def _file_rows(files, *, action_file_id=None, action=None, bound_form=None):
    rows = []
    for deal_file in files:
        archive_form = DealFileActionForm(
            prefix=f"file-{deal_file.pk}-archive",
            initial={"action": DealFileEvent.Action.ARCHIVE},
            expected_action=DealFileEvent.Action.ARCHIVE,
        )
        restore_form = DealFileActionForm(
            prefix=f"file-{deal_file.pk}-restore",
            initial={"action": DealFileEvent.Action.RESTORE},
            expected_action=DealFileEvent.Action.RESTORE,
        )
        if bound_form is not None and deal_file.pk == action_file_id:
            if action == DealFileEvent.Action.ARCHIVE:
                archive_form = bound_form
            elif action == DealFileEvent.Action.RESTORE:
                restore_form = bound_form
        archive_events = getattr(deal_file, "archive_events", [])
        rows.append({
            "file": deal_file,
            "archive_form": archive_form,
            "restore_form": restore_form,
            "archive_event": archive_events[0] if archive_events else None,
        })
    return rows


def _render_files_page(
    request,
    deal,
    *,
    upload_form=None,
    action_form=None,
    action_file_id=None,
    action=None,
    status=200,
):
    files = list(_files_for_member(request, deal))
    active = [file for file in files if file.archived_at is None]
    archived = [file for file in files if file.archived_at is not None]
    return render(
        request,
        "documents/deal_files.html",
        context(
            request,
            deal=deal,
            upload_form=upload_form or SupportingFileUploadForm(),
            action_form=action_form,
            action_error_file_id=action_file_id,
            active_files=_file_rows(
                active,
                action_file_id=action_file_id,
                action=action,
                bound_form=action_form,
            ),
            archived_files=_file_rows(
                archived,
                action_file_id=action_file_id,
                action=action,
                bound_form=action_form,
            ) if request.member.can_manage_inventory else [],
        ),
        status=status,
    )


@private_no_store
@member_view
def deal_files(request, pk):
    _gate_closed()
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])
    if request.method == "POST":
        require_editor(request)
    deal = _scoped_deal(request, pk)

    if request.method == "GET":
        return _render_files_page(request, deal)

    form = SupportingFileUploadForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            deal_file, created = upload_deal_file(
                deal_id=deal.pk,
                dealership_id=request.member.dealership_id,
                actor=request.user,
                title=form.cleaned_data["title"],
                upload_key=form.cleaned_data["upload_key"],
                pdf_bytes=form.cleaned_data["pdf_file"],
            )
        except FileWorkflowError as error:
            form.add_error(None, str(error))
            if isinstance(error, UploadKeyConflict):
                form.upload_key_conflict = True
        else:
            if created:
                messages.success(request, "Supporting file added to this draft.")
            else:
                messages.info(request, "This upload was already saved. Its current archive state was kept.")
            return redirect("deal_files", pk=deal.pk)
    return _render_files_page(request, deal, upload_form=form)


@private_no_store
@member_view
def file_action(request, pk, file_pk):
    _gate_closed()
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    require_editor(request)
    deal = _scoped_deal(request, pk)
    deal_file = get_object_or_404(DealFile.objects.filter(deal=deal), pk=file_pk)

    prefix_and_action = None
    for action in (DealFileEvent.Action.ARCHIVE, DealFileEvent.Action.RESTORE):
        prefix = f"file-{deal_file.pk}-{action}"
        if f"{prefix}-action" in request.POST:
            prefix_and_action = (prefix, action)
            break
    if prefix_and_action is None:
        form = DealFileActionForm(
            request.POST,
            prefix=f"file-{deal_file.pk}-archive",
            expected_action=DealFileEvent.Action.ARCHIVE,
        )
        form.add_error(None, "Choose Archive or Restore for this file.")
        return _render_files_page(
            request,
            deal,
            action_form=form,
            action_file_id=deal_file.pk,
            action=DealFileEvent.Action.ARCHIVE,
        )

    prefix, expected_action = prefix_and_action
    form = DealFileActionForm(
        request.POST,
        prefix=prefix,
        expected_action=expected_action,
    )
    if not form.is_valid():
        return _render_files_page(
            request,
            deal,
            action_form=form,
            action_file_id=deal_file.pk,
            action=expected_action,
        )

    try:
        _, changed = change_deal_file_state(
            deal_id=deal.pk,
            dealership_id=request.member.dealership_id,
            file_id=deal_file.pk,
            actor=request.user,
            action=form.cleaned_data["action"],
            reason=form.cleaned_data["reason"],
        )
    except (DealFile.DoesNotExist, DraftDeal.DoesNotExist):
        raise Http404
    except FileWorkflowError as error:
        form.add_error(None, str(error))
        return _render_files_page(
            request,
            deal,
            action_form=form,
            action_file_id=deal_file.pk,
            action=expected_action,
        )

    if changed and expected_action == DealFileEvent.Action.ARCHIVE:
        messages.success(request, "Supporting file archived. Its bytes and history are retained.")
    elif changed:
        messages.success(request, "Supporting file restored.")
    else:
        messages.info(request, "This file was already in that state. No history entry was added.")
    return redirect("deal_files", pk=deal.pk)


def _set_download_headers(response, filename, byte_size):
    response["Content-Type"] = "application/octet-stream"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = str(byte_size)
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox"
    return response


@private_no_store
@member_view
def file_download(request, pk, file_pk):
    _gate_closed()
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])

    opened_file = None
    try:
        with transaction.atomic():
            deal = get_object_or_404(
                DraftDeal.objects.select_for_update().filter(
                    dealership_id=request.member.dealership_id
                ),
                pk=pk,
            )
            files = DealFile.objects.filter(deal=deal)
            if not request.member.can_manage_inventory:
                files = files.filter(archived_at__isnull=True)
            deal_file = get_object_or_404(files, pk=file_pk)

            # Authorization and active/archive checks above precede any storage access.
            try:
                opened_file = deal_file.blob.open("rb")
            except FileNotFoundError as error:
                raise Http404 from error

            DealFileEvent.objects.create(
                file=deal_file,
                actor=request.user,
                action=DealFileEvent.Action.DOWNLOAD,
            )
    except BaseException:
        if opened_file is not None:
            opened_file.close()
        raise

    filename = f"deal-file-{deal_file.pk}.pdf"
    if request.method == "HEAD":
        opened_file.close()
        response = HttpResponse(status=200)
    else:
        response = FileResponse(
            opened_file,
            as_attachment=True,
            filename=filename,
            content_type="application/octet-stream",
        )
    return _set_download_headers(response, filename, deal_file.byte_size)

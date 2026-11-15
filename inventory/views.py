# SPDX-License-Identifier: MPL-2.0
import posixpath
from functools import wraps
from pathlib import Path, PurePosixPath

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, F, Exists, OuterRef, Prefetch, Count, Subquery
from django.db.models.functions import Cast, Round
from django.db.models import BigIntegerField
from .reconditioning import with_cost_totals
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponseForbidden, HttpResponseNotFound
from django.conf import settings
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from core.models import AuditEvent, Dealership
from core.access import member_view, context, require_editor
from .forms import VehicleForm, VehiclePhotoForm
from .models import Vehicle, VehiclePhoto
from .photos import add_photos, change_photo
from core.filter_views import filter_context
from .filters import SCHEMA
from .vin_matching import normalized_vin_expression

def vehicles(request):
    return Vehicle.objects.filter(dealership=request.member.dealership)

@member_view
def today(request):
    from deals.models import DealFollowUp
    from django.utils import timezone
    tasks = DealFollowUp.objects.filter(deal__dealership=request.member.dealership, assigned_to=request.user, completed_at__isnull=True).order_by(F("due_on").asc(nulls_last=True), "pk")
    return render(request, "inventory/today.html", context(request, follow_ups=tasks[:5], today=timezone.localdate()))

@member_view
def vehicle_list(request):
    filters = filter_context(request, SCHEMA)
    state = filters["filter_state"]
    stock = with_cost_totals(vehicles(request)).annotate(filter_total_cost=Cast(Round(F("acquisition_cost") * 100), BigIntegerField()) + Cast(Round(F("recon_cost") * 100), BigIntegerField()) + F("registered_cost_cents"), filter_has_photos=Exists(VehiclePhoto.objects.filter(vehicle_id=OuterRef("pk"), archived_at__isnull=True)))
    scope = state.extra.get("scope", "")
    if scope in ("active", "missing-title", "attention"):
        stock = stock.exclude(status=Vehicle.Status.SOLD)
    if scope == "missing-title":
        stock = stock.filter(title_received=False)
    elif scope == "attention":
        stock = stock.filter(Q(title_received=False) | Q(title_brand=Vehicle.Brand.UNKNOWN))
    query = state.query
    if query:
        for word in query.split():
            match = Q(stock_number__icontains=word) | Q(vin__icontains=word) | Q(make__icontains=word) | Q(model__icontains=word)
            if word.isascii() and word.isdecimal() and len(word) <= 4:
                match |= Q(year=int(word))
            stock = stock.filter(match)
    status = state.extra.get("status", "")
    if status in Vehicle.Status.values:
        stock = stock.filter(status=status)
    stock = state.apply(stock).prefetch_related(Prefetch("photos", queryset=VehiclePhoto.objects.filter(archived_at__isnull=True).order_by("-is_primary", "pk"), to_attr="visible_photos"))
    page = Paginator(stock, 25).get_page(request.GET.get("page"))
    scope_labels = {"active": "Active inventory", "missing-title": "Active · missing titles", "attention": "Active · title follow-up"}
    quick_label = " · ".join(label for label in (scope_labels.get(scope), dict(Vehicle.Status.choices).get(status)) if label)
    return render(request, "inventory/list.html", context(request, **filters, vehicles=page, page_obj=page, query=query, scope=scope, status=status, quick_filter_label=quick_label, duplicate_vin_review_enabled=settings.DEBUG))


@never_cache
@member_view
@require_safe
def duplicate_vin_report(request):
    """Review matching stored VINs, including sold stock, without changing them."""
    if not settings.DEBUG:
        raise Http404
    stock = vehicles(request).annotate(normalized_vin=normalized_vin_expression()).exclude(normalized_vin='')
    duplicates = stock.order_by().values('normalized_vin').annotate(total=Count('pk')).filter(total__gt=1).values('normalized_vin')
    rows = stock.filter(normalized_vin__in=Subquery(duplicates)).order_by('normalized_vin', 'stock_number', 'pk')
    page = Paginator(rows, 25).get_page(request.GET.get('page'))
    return render(request, 'inventory/duplicate_vin_report.html', context(request, page_obj=page, vehicles=page))

@member_view
def vehicle_detail(request, pk, photo_form=None):
    vehicle = get_object_or_404(vehicles(request), pk=pk)
    all_photos = list(vehicle.photos.all())
    vehicle.visible_photos = [photo for photo in all_photos if photo.archived_at is None]
    events = AuditEvent.objects.filter(dealership=request.member.dealership, vehicle=vehicle).select_related("actor")[:20]
    source_trade = getattr(vehicle, "source_trade", None)
    if source_trade and source_trade.deal.dealership_id != request.member.dealership_id:
        source_trade = None
    return render(request, "inventory/detail.html", context(request, vehicle=vehicle, source_trade=source_trade, events=events, photos=vehicle.visible_photos, hidden_photos=[photo for photo in all_photos if photo.archived_at is not None] if request.member.can_manage_inventory else [], photo_form=photo_form or VehiclePhotoForm()))


@member_view
@require_POST
def vehicle_photo_upload(request, pk):
    require_editor(request)
    vehicle = get_object_or_404(vehicles(request), pk=pk)
    form = VehiclePhotoForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            add_photos(vehicle, form.cleaned_data["photos"], actor=request.user)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Vehicle photos added.")
            return redirect(reverse("vehicle_detail", args=[pk]) + "#photos")
    return vehicle_detail(request, pk, photo_form=form)


@member_view
@require_POST
def vehicle_photo_action(request, pk):
    require_editor(request)
    photo = get_object_or_404(VehiclePhoto, pk=pk, vehicle__dealership=request.member.dealership)
    try:
        change_photo(photo, request.POST.get("action"), actor=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Vehicle photos updated.")
    return redirect(reverse("vehicle_detail", args=[photo.vehicle_id]) + "#photos")


def _private_photo_response(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        request._railet_private_response = True
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


@_private_photo_response
@member_view
@require_safe
def vehicle_photo_file(request, pk, thumbnail=False):
    choices = VehiclePhoto.objects.filter(vehicle__dealership=request.member.dealership)
    if not request.member.can_manage_inventory:
        choices = choices.filter(archived_at__isnull=True)
    photo = get_object_or_404(choices, pk=pk)
    field = photo.thumbnail if thumbnail else photo.image
    name = field.name or ""
    path = PurePosixPath(name)
    if (not name or "\\" in name or str(path) != name or path.is_absolute()
            or len(path.parts) != 2 or path.parts[0] != "vehicles" or ".." in path.parts):
        raise Http404
    for image_name, thumb_name in VehiclePhoto.objects.exclude(vehicle__dealership_id=request.member.dealership_id).values_list("image", "thumbnail").iterator(chunk_size=1000):
        if any(value and posixpath.normpath(value) == name for value in (image_name, thumb_name)):
            raise Http404
    try:
        root = Path(field.storage.location)
        raw = Path(field.storage.path(name))
        if (root.is_symlink() or raw.is_symlink() or raw.parent.is_symlink()
                or not raw.resolve(strict=True).is_relative_to(root.resolve(strict=True))):
            raise Http404
        response = FileResponse(field.open("rb"), content_type="image/jpeg", filename="vehicle-photo.jpg")
    except (OSError, ValueError):
        raise Http404("Photo unavailable")
    return response

def save_vehicle(request, pk=None):
    if not request.member.can_manage_inventory:
        raise PermissionDenied("Inventory changes require an owner or inventory staff role.")
    with transaction.atomic():
        if request.method == "POST":
            # Serialize VIN checks with trade intake and other ordinary inventory saves.
            Dealership.objects.select_for_update().get(pk=request.member.dealership_id)
        choices = vehicles(request)
        if pk:
            if request.method == "POST":
                choices = choices.select_for_update()
            vehicle = get_object_or_404(choices, pk=pk)
        else:
            vehicle = Vehicle(dealership=request.member.dealership)
        before = {field: str(getattr(vehicle, field)) for field in VehicleForm.Meta.fields} if pk else {}
        form = VehicleForm(
            request.POST if request.method == "POST" else None,
            instance=vehicle,
            dealership=request.member.dealership,
        )
        if request.method == "POST" and form.is_valid():
            if pk and form.cleaned_data["revision"] != vehicle.revision:
                form.add_error(None, "Someone updated this vehicle while you were editing. Your entries are still below. Open the latest vehicle in a new tab, compare the changes, then reload before saving again.")
                return render_vehicle_form(request, form, vehicle, editing=True, status=409)
            # Dealership is assigned by the server and must participate in constraint validation.
            try:
                form.instance.full_clean()
            except ValidationError as error:
                form.add_error(None, error)
            else:
                if pk:
                    form.instance.revision += 1
                duplicate_review = form.duplicate_review_metadata
                saved = form.save()
                changes = {field: {"before": before.get(field), "after": str(getattr(saved, field))} for field in VehicleForm.Meta.fields if before.get(field) != str(getattr(saved, field))}
                if duplicate_review is not None:
                    changes["duplicate_vin_review"] = {
                        "before": None,
                        "after": duplicate_review,
                    }
                if changes:
                    AuditEvent.objects.create(dealership=request.member.dealership, actor=request.user, vehicle=saved, action="updated" if pk else "created", changes=changes)
                messages.success(request, "Vehicle saved.")
                return redirect("vehicle_detail", pk=saved.pk)
    return render_vehicle_form(request, form, vehicle, editing=bool(pk))


def render_vehicle_form(request, form, vehicle, *, editing, status=200):
    matches = form.duplicate_matches
    return render(
        request,
        "inventory/form.html",
        context(
            request,
            form=form,
            editing=editing,
            vehicle=vehicle,
            duplicate_matches=matches[:20],
            duplicate_match_count=len(matches),
            duplicate_match_display_limit=20,
        ),
        status=status,
    )

@member_view
def vehicle_create(request):
    return save_vehicle(request)

@member_view
def vehicle_edit(request, pk):
    return save_vehicle(request, pk)

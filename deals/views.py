# SPDX-License-Identifier: MPL-2.0
from django.contrib import messages
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from core.access import member_view, context, require_editor
from customers.forms import CustomerForm
from customers.services import save_customer
from .forms import DraftDealForm, DraftWorksheetForm, DraftFinanceProposalForm
from .models import DraftDeal, MONEY_FIELDS, DraftFinanceProposal, FINANCING_TYPES, DealType
from .queries import search_drafts
from .services import persist_draft
from .worksheet import draft_totals
from .filters import SCHEMA
from core.filter_views import filter_context
from inventory.models import VehiclePhoto

def records(request):
    return DraftDeal.objects.filter(dealership=request.member.dealership)

@member_view
def deal_list(request):
    filters = filter_context(request, SCHEMA)
    state = filters["filter_state"]
    query = state.query
    drafts = state.apply(search_drafts(request.member.dealership, query)).select_related("vehicle", "buyer", "co_buyer").prefetch_related(Prefetch("vehicle__photos", queryset=VehiclePhoto.objects.filter(archived_at__isnull=True).order_by("-is_primary", "pk"), to_attr="visible_photos"))
    page = Paginator(drafts, 25).get_page(request.GET.get("page"))
    return render(request, "deals/list.html", context(request, **filters, deals=page, page_obj=page, query=query))

@member_view
def deal_detail(request, pk):
    if request.method == "POST":
        require_editor(request)
    status = 200
    active_section = request.POST.get("active_section", "structure")
    if active_section not in ("structure", "notes", "history"):
        active_section = "structure"
    with transaction.atomic():
        choices = records(request)
        choices = choices.select_for_update() if request.method == "POST" else choices.select_related("vehicle", "buyer", "co_buyer")
        deal = get_object_or_404(choices, pk=pk)
        form = DraftWorksheetForm(
            request.POST if request.method == "POST" else None,
            instance=deal, read_only=not request.member.can_manage_inventory,
        )
        existing = {proposal.kind: proposal for proposal in deal.finance_proposals.all()}
        proposals = []
        for kind in FINANCING_TYPES:
            submitted = request.method == "POST" and request.POST.get(f"{kind}-included") == "1"
            proposal_form = DraftFinanceProposalForm(
                request.POST if submitted else None, prefix=kind,
                instance=existing.get(kind) or DraftFinanceProposal(deal=deal, kind=kind),
                read_only=not request.member.can_manage_inventory,
            )
            proposals.append({"kind": kind, "label": DealType(kind).label, "form": proposal_form})
        if request.method == "POST":
            valid = form.is_valid()
            for proposal in proposals:
                if proposal["form"].is_bound:
                    valid = proposal["form"].is_valid() and valid
        else:
            valid = False
        changed_proposals = [item["form"] for item in proposals if item["form"].is_bound and item["form"].has_changed()]
        if valid:
            if form.cleaned_data["revision"] != deal.revision:
                form.add_error(None, "Someone saved this deal while you were working. Your entries are kept below. Compare them with the latest deal before saving again.")
                status = 409
            elif not changed_proposals and not any(name in form.changed_data for name in (*MONEY_FIELDS, "notes", "deal_type")):
                messages.info(request, "This deal is already up to date.")
                return redirect(reverse("deal_detail", args=[deal.pk]) + "#deal-" + active_section)
            else:
                deal.revision += 1
                persist_draft(deal, actor=request.user, proposals=changed_proposals)
                messages.success(request, "Deal saved.")
                return redirect(reverse("deal_detail", args=[deal.pk]) + "#deal-" + active_section)
    events = deal.events.select_related("actor")[:20]
    amounts = {name: form.cleaned_data.get(name) if form.is_bound else getattr(deal, name) for name in MONEY_FIELDS}
    totals = draft_totals(amounts) if all(value is not None for value in amounts.values()) else None
    fee_fields, trade_fields = ("tax", "title_registration", "dealer_fee"), ("trade_allowance", "trade_payoff")
    return render(request, "deals/detail.html", context(
        request, active_trade=deal.trades.filter(archived_at__isnull=True).select_related("inventory_vehicle").first(), trade_intake_enabled=settings.TRADE_INTAKE_DEMO_ENABLED, deal_files_enabled=settings.DEAL_FILES_DEMO_ENABLED,
        deal=deal, form=form, proposals=proposals, proposal_errors=any(item["form"].errors for item in proposals), deal_type_label=dict(DealType.choices).get(form["deal_type"].value(), "Not chosen"), events=events, totals=totals, conflict=status == 409, active_section=active_section,
        fees_open=any(form[name].errors or amounts[name] for name in fee_fields),
        trade_open=deal.trades.filter(archived_at__isnull=True).exists() or any(form[name].errors or amounts[name] for name in trade_fields),
    ), status=status)

def already_saved(request, deal):
    messages.info(request, "This draft was already saved. You can edit its worksheet below.")
    return redirect("deal_detail", pk=deal.pk)

def editor(request, pk=None):
    require_editor(request)
    with transaction.atomic():
        deal = get_object_or_404(records(request).select_for_update(), pk=pk) if pk else DraftDeal(dealership=request.member.dealership)
        posted = request.POST if request.method == "POST" else None
        form = DraftDealForm(posted, instance=deal, dealership=request.member.dealership)
        if not pk and request.method == "GET":
            for parameter, field_name in (("vehicle", "vehicle"), ("buyer", "buyer")):
                try:
                    selected = form.fields[field_name].clean(request.GET.get(parameter, ""))
                except ValidationError:
                    continue
                if selected:
                    form.initial[field_name] = selected.pk
        mode = form["customer_mode"].value() or "existing"
        new_customer = CustomerForm(posted if mode == "new" else None, prefix="new", dealership=request.member.dealership)
        status = 200
        if request.method == "POST":
            valid = form.is_valid()
            if mode == "new":
                valid = new_customer.is_valid() and valid
            creation_key = form.cleaned_data.get("submission_key") if not pk else None
            if creation_key:
                saved = records(request).filter(creation_key=creation_key).first()
                if saved:
                    return already_saved(request, saved)
            if pk and valid and form.cleaned_data["revision"] != deal.revision:
                form.add_error(None, "This draft changed while you were editing. Your entries are preserved. Compare the latest draft before reloading.")
                valid, status = False, 409
            if valid:
                try:
                    with transaction.atomic():
                        if mode == "new":
                            deal.buyer = save_customer(new_customer, actor=request.user, dealership=request.member.dealership)
                        else:
                            deal.buyer = form.cleaned_data["buyer"]
                        deal.dealership = request.member.dealership
                        if pk:
                            deal.revision += 1
                        else:
                            deal.creation_key = creation_key
                        persist_draft(deal, actor=request.user)
                except IntegrityError:
                    if creation_key:
                        saved = records(request).filter(creation_key=creation_key).first()
                        if saved:
                            return already_saved(request, saved)
                    raise
                messages.success(request, "Draft deal saved. No payment was taken and the vehicle remains in inventory.")
                return redirect("deal_detail", pk=deal.pk)
    has_worksheet_details = (
        bool(deal.notes)
        or any(getattr(deal, name) for name in MONEY_FIELDS)
        or any(form[name].errors for name in (*MONEY_FIELDS, "notes"))
    )
    return render(request, "deals/form.html", context(request, form=form, new_customer=new_customer, mode=mode, editing=bool(pk), deal=deal, has_worksheet_details=has_worksheet_details), status=status)

@member_view
def deal_create(request):
    return editor(request)

@member_view
def deal_edit(request, pk):
    return editor(request, pk)

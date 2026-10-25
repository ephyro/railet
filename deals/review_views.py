# SPDX-License-Identifier: MPL-2.0
from django.http import Http404, HttpResponseNotAllowed
from django.db import transaction
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from core.access import context, member_view
from .models import DealType, DraftDeal, FINANCING_TYPES, MONEY_FIELDS
from .review import build_review_reminders, money_text
from .worksheet import draft_totals


def _record_link(request, edit_route, view_route, pk):
    if request.member.can_manage_inventory:
        return reverse(edit_route, args=[pk])
    return reverse(view_route, args=[pk])


@member_view
@never_cache
def review_detail(request, pk):
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])

    with transaction.atomic():
        return _render_review(request, pk)


def _render_review(request, pk):
    dealership_id = request.member.dealership_id
    deal = get_object_or_404(
        DraftDeal.objects.filter(dealership_id=dealership_id).select_related(
            "vehicle", "buyer", "co_buyer"
        ).select_for_update(of=("self",)),
        pk=pk,
    )

    # Keep the scoped parent query from exposing a related record if stale or
    # manually imported data contains an invalid cross-dealership reference.
    related_records = [deal.vehicle, deal.buyer]
    if deal.co_buyer_id:
        related_records.append(deal.co_buyer)
    if any(record.dealership_id != dealership_id for record in related_records):
        raise Http404

    active_trade = (
        deal.trades.filter(archived_at__isnull=True)
        .select_related("inventory_vehicle")
        .first()
    )
    selected_proposal = None
    if deal.deal_type in FINANCING_TYPES:
        selected_proposal = deal.finance_proposals.filter(kind=deal.deal_type).first()

    amounts = {name: getattr(deal, name) for name in MONEY_FIELDS}
    totals = draft_totals(amounts) if all(value is not None for value in amounts.values()) else None
    worksheet_rows = [
        ("Vehicle price", money_text(deal.sale_price)),
        ("Sales tax entered", money_text(deal.tax)),
        ("Title and registration fees", money_text(deal.title_registration)),
        ("Dealer fee", money_text(deal.dealer_fee)),
        ("Trade allowance", money_text(deal.trade_allowance)),
        ("Estimated trade payoff", money_text(deal.trade_payoff)),
        ("Planned down payment", money_text(deal.down_payment)),
    ]
    if totals is not None:
        worksheet_rows.append(("Trade payoff less allowance", money_text(totals["trade_adjustment"])))

    proposal_rows = []
    if selected_proposal:
        rate = selected_proposal.annual_contract_rate
        proposal_rows = [
            ("Proposed interest method", selected_proposal.get_interest_method_display()),
            ("Creditor or funding source", selected_proposal.creditor_name.strip() if selected_proposal.creditor_name.strip() else "Not recorded"),
            (
                "Payment frequency",
                selected_proposal.get_payment_frequency_display()
                if selected_proposal.payment_frequency
                else "Not recorded",
            ),
            (
                "Payment count",
                str(selected_proposal.payment_count)
                if selected_proposal.payment_count is not None
                else "Not recorded",
            ),
            (
                "Annual contract rate entered (not APR)",
                f"{rate:.4f}%" if rate is not None else "Not recorded",
            ),
            (
                "First payment date",
                selected_proposal.first_payment_date.strftime("%b %-d, %Y")
                if selected_proposal.first_payment_date
                else "Not recorded",
            ),
        ]

    links = {
        "deal": _record_link(request, "deal_edit", "deal_detail", deal.pk),
        "proposal": reverse("deal_detail", args=[deal.pk]) + "#deal-structure",
        "vehicle": _record_link(request, "vehicle_edit", "vehicle_detail", deal.vehicle_id),
        "buyer": _record_link(request, "customer_edit", "customer_detail", deal.buyer_id),
        "trade": _record_link(request, "trade_edit", "deal_detail", deal.pk),
    }
    if deal.co_buyer_id:
        links["co_buyer"] = _record_link(request, "customer_edit", "customer_detail", deal.co_buyer_id)
    else:
        links["co_buyer"] = links["deal"]

    reminders = build_review_reminders(deal, active_trade, selected_proposal, links)
    trade_inventory_is_local = bool(
        active_trade
        and active_trade.inventory_vehicle_id
        and active_trade.inventory_vehicle.dealership_id == dealership_id
    )

    return render(
        request,
        "deals/review.html",
        context(
            request,
            deal=deal,
            active_trade=active_trade,
            trade_inventory_is_local=trade_inventory_is_local,
            selected_proposal=selected_proposal,
            deal_type_label=dict(DealType.choices).get(deal.deal_type, "Not chosen"),
            worksheet_rows=worksheet_rows,
            worksheet_balance=money_text(totals["balance"]) if totals is not None else "Not recorded",
            worksheet_available=totals is not None,
            proposal_rows=proposal_rows,
            review_links=links,
            reminders=reminders,
        ),
    )

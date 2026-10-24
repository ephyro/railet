# SPDX-License-Identifier: MPL-2.0
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from core.access import member_view, context, require_editor
from .models import DraftDeal, DraftTradeIn
from .trade_forms import TradeInForm, TradeRemoveForm, TradeIntakeForm
from .trades import save_trade, remove_trade, intake_trade


def scoped_deal(request, pk):
    choices = DraftDeal.objects.filter(dealership=request.member.dealership)
    return get_object_or_404(choices.select_for_update() if request.method == "POST" else choices, pk=pk)


def check_revision(form, deal):
    if form.cleaned_data["revision"] != deal.revision:
        form.add_error(None, "This deal changed while you were working. Your entries are kept. Open the latest deal in a new tab and compare before saving again.")
        return False
    return True


@member_view
def trade_edit(request, pk):
    require_editor(request)
    status = 200
    with transaction.atomic():
        deal = scoped_deal(request, pk)
        trade = deal.trades.filter(archived_at__isnull=True).first() or DraftTradeIn(deal=deal)
        form = TradeInForm(request.POST if request.method == "POST" else None, instance=trade, deal=deal)
        if request.method == "POST" and form.is_valid():
            if not check_revision(form, deal):
                status = 409
            elif trade.pk and not form.has_changed():
                messages.info(request, "This trade is already up to date.")
                return redirect(reverse("deal_detail", args=[deal.pk]) + "#deal-structure")
            else:
                try:
                    save_trade(form, deal=deal, actor=request.user)
                except ValidationError as error:
                    form.add_error(None, " ".join(error.messages))
                else:
                    messages.success(request, "Trade saved. The allowance and estimated payoff are included in the draft totals.")
                    return redirect(reverse("deal_detail", args=[deal.pk]) + "#deal-structure")
    return render(request, "deals/trade_form.html", context(request, deal=deal, trade=trade, form=form), status=status)


@member_view
def trade_remove(request, pk, trade_pk):
    require_editor(request)
    status = 200
    with transaction.atomic():
        deal = scoped_deal(request, pk)
        trade = get_object_or_404(deal.trades, pk=trade_pk, archived_at__isnull=True)
        form = TradeRemoveForm(request.POST if request.method == "POST" else None, initial={"revision": deal.revision})
        if request.method == "POST" and form.is_valid():
            if not check_revision(form, deal):
                status = 409
            else:
                try:
                    remove_trade(trade, deal=deal, actor=request.user, reason=form.cleaned_data["reason"])
                except ValidationError as error:
                    form.add_error(None, " ".join(error.messages))
                else:
                    messages.success(request, "Trade removed from the draft. Its record and saved history are retained.")
                    return redirect("deal_detail", pk=deal.pk)
    return render(request, "deals/trade_action.html", context(request, deal=deal, trade=trade, form=form, removing=True,
                  balance_after=deal.draft_balance + deal.trade_allowance - deal.trade_payoff), status=status)


@member_view
def trade_intake(request, pk, trade_pk):
    require_editor(request)
    if not settings.TRADE_INTAKE_DEMO_ENABLED:
        raise Http404("Trade intake is not enabled.")
    status = 200
    with transaction.atomic():
        deal = scoped_deal(request, pk)
        trade = get_object_or_404(deal.trades, pk=trade_pk, archived_at__isnull=True)
        if trade.inventory_vehicle_id:
            messages.info(request, "This trade already has an inventory record.")
            return redirect("vehicle_detail", pk=trade.inventory_vehicle_id)
        form = TradeIntakeForm(request.POST if request.method == "POST" else None, initial={"revision": deal.revision})
        if request.method == "POST" and form.is_valid():
            if not check_revision(form, deal):
                status = 409
            else:
                try:
                    vehicle = intake_trade(trade, deal=deal, actor=request.user, data=form.cleaned_data)
                except ValidationError as error:
                    form.add_error(None, " ".join(error.messages))
                except IntegrityError:
                    form.add_error(None, "Inventory changed during intake. Check the stock number and VIN, then compare the latest deal before retrying.")
                else:
                    messages.success(request, "Trade added to inventory. The draft remains open; no payoff or payment was recorded.")
                    return redirect("vehicle_detail", pk=vehicle.pk)
    return render(request, "deals/trade_action.html", context(request, deal=deal, trade=trade, form=form, removing=False), status=status)

# SPDX-License-Identifier: MPL-2.0
"""Draft trade operations. Call with the scoped parent locked and revision checked."""
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from inventory.intake import create_trade_vehicle
from .models import TRADE_IDENTITY_FIELDS
from .services import persist_draft


@transaction.atomic
def save_trade(form, *, deal, actor):
    trade = form.save(commit=False)
    if trade.deal_id != deal.pk or trade.archived_at:
        raise ValidationError("Choose an active trade from this draft.")
    trade.full_clean()
    trade.save()
    if deal.tax_context.get("mode")=="fl":deal.tax_context={**deal.tax_context,"trade_confirmed":form.cleaned_data.get("tax_trade_confirmed",False)}
    deal.trade_allowance = form.cleaned_data["trade_allowance"]
    deal.trade_payoff = form.cleaned_data["trade_payoff"]
    deal.revision += 1
    persist_draft(deal, actor=actor, action="trade_saved")
    return trade


@transaction.atomic
def remove_trade(trade, *, deal, actor, reason):
    if trade.deal_id != deal.pk or trade.archived_at:
        raise ValidationError("Choose an active trade from this draft.")
    if balance_without_trade(deal) < 0:
        raise ValidationError("Removing this trade would make the draft balance negative. Adjust the planned down payment or other amounts first.")
    trade.archived_at = timezone.now()
    trade.save(update_fields=["archived_at", "updated_at"])
    deal.trade_allowance = deal.trade_payoff = Decimal("0.00")
    deal.revision += 1
    persist_draft(deal, actor=actor, action="trade_removed", reason=reason)


@transaction.atomic
def intake_trade(trade, *, deal, actor, data):
    if not settings.TRADE_INTAKE_DEMO_ENABLED:
        raise PermissionDenied("Trade intake remains gated pending production review.")
    if trade.deal_id != deal.pk or trade.archived_at:
        raise ValidationError("Choose an active trade from this draft.")
    if trade.inventory_vehicle_id:
        return trade.inventory_vehicle
    missing = [name for name in ("vin", "year", "make", "model") if not getattr(trade, name)]
    if missing:
        raise ValidationError("Add the VIN, year, make and model to the trade before inventory intake. Historical VIN formats are supported.")
    if not data.get("confirm"):
        raise ValidationError("Review acquisition and ownership evidence before adding inventory.")
    trade.full_clean()
    vehicle = create_trade_vehicle(dealership=deal.dealership, actor=actor,
        identity={name: getattr(trade, name) for name in TRADE_IDENTITY_FIELDS},
        stock_number=data["stock_number"], acquisition_cost=data["acquisition_cost"],
        title_received=data["title_received"], source_trade_id=trade.pk)
    trade.inventory_vehicle = vehicle
    trade.full_clean()
    trade.save(update_fields=["inventory_vehicle", "updated_at"])
    deal.revision += 1
    persist_draft(deal, actor=actor, action="trade_intake")
    return vehicle


def balance_without_trade(deal):
    from copy import copy
    from .florida_tax import refresh
    preview=copy(deal);preview.trade_allowance=preview.trade_payoff=Decimal('0.00')
    refresh(preview)
    return preview.draft_balance

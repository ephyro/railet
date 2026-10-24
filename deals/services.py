# SPDX-License-Identifier: MPL-2.0
from django.db import transaction

from .models import DealEvent, MONEY_FIELDS, FINANCING_TYPES, PROPOSAL_FIELDS, TRADE_FIELDS
from django.core.exceptions import ValidationError


@transaction.atomic
def persist_draft(deal, *, actor, proposals=(), action="draft_saved", reason=""):
    # The database arbitrates concurrent creation keys. Other validation runs here.
    deal.full_clean(exclude=["creation_key"])
    deal.save()
    for form in proposals:
        proposal = form.save(commit=False)
        if proposal.kind not in FINANCING_TYPES:
            raise ValidationError("Choose a financing proposal type.")
        if proposal.deal_id and proposal.deal_id != deal.pk:
            raise ValidationError("A financing proposal must belong to this draft.")
        proposal.deal = deal
        proposal.full_clean()
        proposal.save()
    snapshots = {}
    for proposal in deal.finance_proposals.all():
        values = {}
        for name in PROPOSAL_FIELDS:
            value = getattr(proposal, name)
            values[name] = value.isoformat() if name == "first_payment_date" and value else str(value) if name == "annual_contract_rate" and value is not None else value
        snapshots[proposal.kind] = values
    DealEvent.objects.create(
        deal=deal,
        actor=actor,
        snapshot={
            "schema_version": 3,
            "action": action,
            "reason": reason,
            "trades": [
                {"id": trade.pk, "inventory_vehicle_id": trade.inventory_vehicle_id,
                 "archived_at": trade.archived_at.isoformat() if trade.archived_at else None,
                 **{name: value.isoformat() if hasattr(value, "isoformat") else value
                    for name in TRADE_FIELDS for value in [getattr(trade, name)]}}
                for trade in deal.trades.all()
            ],
            "deal_type": deal.deal_type,
            "finance_proposals": snapshots,
            "vehicle_id": deal.vehicle_id,
            "buyer_id": deal.buyer_id,
            "co_buyer_id": deal.co_buyer_id,
            "revision": deal.revision,
            "notes": deal.notes,
            **{name: str(getattr(deal, name)) for name in MONEY_FIELDS},
        },
    )
    return deal

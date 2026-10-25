# SPDX-License-Identifier: MPL-2.0
"""Read interface for synthetic account context, never loan origination."""
from .models import DraftDeal, PROPOSAL_FIELDS


def eligible_account_drafts(*, dealership_id, customer_id):
    return DraftDeal.objects.filter(
        dealership_id=dealership_id, buyer_id=customer_id,
        buyer__dealership_id=dealership_id, vehicle__dealership_id=dealership_id,
        deal_type='bhph', archived_at__isnull=True,
    ).select_related('vehicle', 'buyer')


def account_draft_snapshot(deal):
    proposal = deal.finance_proposals.filter(kind='bhph').first()
    return {
        'schema_version': 1, 'deal_id': deal.pk, 'deal_revision': deal.revision,
        'customer_id': deal.buyer_id, 'vehicle_id': deal.vehicle_id,
        'vehicle': str(deal.vehicle), 'stock_number': deal.vehicle.stock_number,
        'vin': deal.vehicle.vin, 'title_brand': deal.vehicle.get_title_brand_display(),
        'proposed_terms': {name: str(getattr(proposal, name)) if getattr(proposal, name) is not None else '' for name in PROPOSAL_FIELDS} if proposal else {},
        'interest_method': proposal.get_interest_method_display() if proposal else 'Not chosen',
        'term_rows': [(label, str(getattr(proposal, name)) if getattr(proposal, name) is not None else '') for name, label in [('creditor_name', 'Creditor'), ('payment_count', 'Number of payments'), ('annual_contract_rate', 'Annual contract rate, not APR (%)'), ('first_payment_date', 'First payment date')]] if proposal else [],
        'frequency': proposal.get_payment_frequency_display() if proposal and proposal.payment_frequency else 'Not entered',
    }

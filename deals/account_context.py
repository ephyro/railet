# SPDX-License-Identifier: MPL-2.0
"""Read interface for synthetic account context, never loan origination."""
from .models import DraftDeal, PROPOSAL_FIELDS


def eligible_account_drafts(*, dealership_id, customer_id):
    return DraftDeal.objects.filter(
        dealership_id=dealership_id, buyer_id=customer_id,
        buyer__dealership_id=dealership_id, vehicle__dealership_id=dealership_id,
        deal_type='bhph', archived_at__isnull=True, demo_completion__isnull=True,
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


def completed_account_snapshot(deal):
    """Build servicing context from a verified completion and frozen deal terms."""
    from django.core.exceptions import ValidationError
    from documents.packets import build_snapshot
    from .completion import verified_snapshot, check_gate
    check_gate()
    completion = deal.demo_completion
    saved = verified_snapshot(completion)
    from .models import DemoCompletionVoid
    if DemoCompletionVoid.objects.filter(completion=completion).exists():
        raise ValidationError("This completion rehearsal has been voided.")
    if deal.deal_type != 'bhph' or saved.get('deal_type') != 'Buy here, pay here':
        raise ValidationError('A completed BHPH rehearsal is required.')
    # The proposal rows are database-frozen by completion guards. Verify them
    # against the captured packet before reading the structured values.
    if not saved.get('proposal') or build_snapshot(deal).get('proposal') != saved.get('proposal'):
        raise ValidationError('Frozen financing terms failed verification.')
    buyer = saved['buyer']
    vehicle = saved['vehicle']
    if buyer['record_id'] != deal.buyer_id or vehicle['record_id'] != deal.vehicle_id:
        raise ValidationError('Frozen parties do not match the completed deal.')
    snapshot = account_draft_snapshot(deal)
    snapshot.update({
        'schema_version': 2, 'source': 'completed-rehearsal',
        'completion_id': completion.pk, 'completion_review_sha256': completion.review_sha256,
        'deal_revision': completion.source_revision, 'customer_name': buyer['name'],
        'vehicle': vehicle['description'], 'stock_number': vehicle['stock_number'],
        'vin': '' if vehicle['facts']['VIN'] == 'Not recorded' else vehicle['facts']['VIN'],
        'title_brand': vehicle['facts']['Title brand as recorded'],
    })
    return snapshot

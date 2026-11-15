# SPDX-License-Identifier: MPL-2.0
"""Internal synthetic completion; no live sale, document approval or origination."""
from copy import copy, deepcopy
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.urls import reverse
from core.models import Dealership, Membership
from inventory.models import Vehicle
from documents.packets import build_snapshot, locked_source, source_digest, digest, create_packet, PacketChanged
from .models import DemoDealCompletion, DraftDeal, DealEvent, FINANCING_TYPES, MONEY_FIELDS


class CompletionChanged(ValidationError):
    pass


def check_gate():
    if not getattr(settings, 'DEMO_COMPLETION_ENABLED', False) or not getattr(settings, 'DEMO_PACKETS_ENABLED', False):
        raise Http404


def assert_open(deal):
    if DemoDealCompletion.objects.filter(deal_id=deal.pk).exists():
        raise ValidationError('This completed rehearsal is frozen. Open its completion record; use a new draft to practice different figures.')


def _source(deal):
    if not isinstance(deal.tax_context, dict):
        raise CompletionChanged('Review the saved tax information before completing this rehearsal.')
    trade=deal.trades.filter(archived_at__isnull=True).select_related('inventory_vehicle').first()
    if trade and trade.inventory_vehicle_id and trade.inventory_vehicle.dealership_id != deal.dealership_id:
        raise Http404
    snapshot=build_snapshot(deal)
    files=list(deal.supporting_files.filter(archived_at__isnull=True).order_by('pk').values('pk','title','sha256','byte_size')[:501])
    if len(files)>500:
        raise CompletionChanged('This rehearsal supports up to 500 active supporting files. Review the file set first.')
    metadata={'files':files,'vehicle_status':deal.vehicle.status,'deal_notes':deal.notes,'trade_notes':trade.notes if trade else '',
              'revisions':{'deal':deal.revision,'vehicle':deal.vehicle.revision,'buyer':deal.buyer.revision,'co_buyer':deal.co_buyer.revision if deal.co_buyer else None},
              'deal_type_code':deal.deal_type}
    blockers=[]
    def block(title, anchor='deal-structure'):
        blockers.append({'title':title,'url':reverse('deal_detail',args=[deal.pk])+'#'+anchor})
    if deal.archived_at: block('Restore this archived draft before rehearsing completion.')
    if deal.deal_type=='undecided': block('Choose Cash, Outside financing, or Buy here, pay here.')
    if deal.sale_price <= 0: block('Enter a positive vehicle price for this rehearsal.')
    if deal.draft_balance < 0: block('Correct the negative draft balance before continuing.')
    if deal.vehicle.status=='sold': block('This stock record is already marked sold. Review the vehicle selection.')
    if deal.tax_context.get('mode') not in (None,'manual','fl'):
        block('Review the unsupported saved tax profile before continuing.')
    if deal.tax_context.get('mode')=='fl':
        from .florida_tax import refresh
        fresh=copy(deal);fresh.tax_context=deepcopy(deal.tax_context)
        try:
            refresh(fresh)
            if fresh.tax!=deal.tax or fresh.tax_context!=deal.tax_context:
                block('Recalculate and save the Florida draft tax before continuing.')
        except ValidationError:
            block('Review the Florida draft tax inputs before continuing.')
    if deal.deal_type in FINANCING_TYPES:
        proposal=deal.finance_proposals.filter(kind=deal.deal_type).first()
        if not proposal:
            block('Save the financing proposal for the selected deal type.')
        else:
            try:proposal.full_clean()
            except ValidationError:block('Correct the invalid saved financing proposal before continuing.')
            names=['interest_method','creditor_name','payment_frequency','payment_count','first_payment_date']
            names.append('illustration_finance_charge' if proposal.interest_method=='precomputed' else 'annual_contract_rate')
            missing=[name for name in names if getattr(proposal,name) is None or getattr(proposal,name)=='']
            if missing:
                labels={'interest_method':'interest method','creditor_name':'creditor or lender',
                        'payment_frequency':'payment frequency','payment_count':'number of payments',
                        'first_payment_date':'first payment date','illustration_finance_charge':'precomputed finance charge',
                        'annual_contract_rate':'annual contract rate'}
                block('Complete the missing financing terms: '+', '.join(labels[name] for name in missing)+'.')
    return {'snapshot':snapshot,'metadata':metadata,'blockers':blockers,
            'review_sha256':source_digest({'snapshot':snapshot,'metadata':metadata}),
            'source_sha256':source_digest(snapshot)}


@transaction.atomic
def preview(*, dealership_id, deal_id):
    check_gate()
    Dealership.objects.select_for_update().get(pk=dealership_id)
    try:
        return _source(locked_source(dealership_id,deal_id))
    except (DraftDeal.DoesNotExist, Vehicle.DoesNotExist) as error:
        raise Http404 from error


@transaction.atomic
def complete(*, dealership_id, deal_id, actor, creation_key, expected_review, review_notes='', reviewed=False, demo_confirmed=False):
    check_gate()
    Dealership.objects.select_for_update().get(pk=dealership_id)
    if not Membership.objects.select_for_update().filter(user=actor,dealership_id=dealership_id,role__in=['owner','staff']).exists():
        raise PermissionDenied
    prior=DemoDealCompletion.objects.filter(deal_id=deal_id,deal__dealership_id=dealership_id).first()
    if prior:
        if prior.creation_key==creation_key and prior.actor_id==actor.pk and prior.review_sha256==expected_review and prior.review_notes==review_notes.strip():
            return prior
        raise CompletionChanged('This rehearsal is already completed. Open the frozen completion record.')
    if DemoDealCompletion.objects.filter(creation_key=creation_key).exists():
        raise CompletionChanged('This confirmation key has already been used. Review again before saving.')
    try:
        deal=locked_source(dealership_id,deal_id)
    except (DraftDeal.DoesNotExist, Vehicle.DoesNotExist) as error:
        raise Http404 from error
    source=_source(deal)
    if source['review_sha256'] != expected_review:
        raise CompletionChanged('The deal, a linked record, or supporting files changed after review. Review the refreshed figures before confirming again.')
    if source['blockers']:
        raise CompletionChanged('Fix the items listed before completing this rehearsal.')
    notes=review_notes.strip()
    if not reviewed or not demo_confirmed:
        raise CompletionChanged('Confirm the review and the rehearsal-only effects before saving.')
    if len(notes)>1000 or (source['snapshot']['reminders'] and not notes):
        raise CompletionChanged('Add a review note explaining the remaining reminders, up to 1,000 characters.')
    try:
        packet,_=create_packet(dealership_id=dealership_id,deal_id=deal_id,actor=actor,creation_key=creation_key,expected_source=source['source_sha256'])
    except PacketChanged as error:
        raise CompletionChanged(str(error)) from error
    record=DemoDealCompletion.objects.create(deal=deal,packet=packet,source_revision=deal.revision,
        source_sha256=source['source_sha256'],artifact_sha256=packet.artifact_sha256,review_sha256=source['review_sha256'],
        metadata=source['metadata'],review_notes=notes,creation_key=creation_key,actor=actor)
    DealEvent.objects.create(deal=deal,actor=actor,snapshot={'schema_version':7,'action':'completion_rehearsed','revision':deal.revision,
        'completion_id':record.pk,'packet_id':packet.pk,'review_sha256':record.review_sha256,'reason':notes,
        'deal_type':deal.deal_type,'vehicle_id':deal.vehicle_id,'buyer_id':deal.buyer_id,'co_buyer_id':deal.co_buyer_id,
        'tax_context':deal.tax_context,**{name:str(getattr(deal,name)) for name in MONEY_FIELDS}})
    return record


def verified_snapshot(record):
    packet=record.packet
    if packet.deal_id!=record.deal_id or packet.source_sha256!=record.source_sha256 or source_digest(packet.snapshot)!=record.source_sha256 or packet.artifact_sha256!=record.artifact_sha256 or digest(packet.html)!=record.artifact_sha256 or source_digest({'snapshot':packet.snapshot,'metadata':record.metadata})!=record.review_sha256:
        raise CompletionChanged('The stored completion record failed its integrity check. Contact your administrator.')
    return packet.snapshot


def _void_review(record):
    """Digest immutable facts; verify retained packet before displaying or writing."""
    verified_snapshot(record)
    return source_digest({'completion_id': record.pk, 'deal_id': record.deal_id,
                          'review_sha256': record.review_sha256,
                          'artifact_sha256': record.artifact_sha256})


def _void_context(dealership_id, deal_id, actor):
    from finance.account_services import completion_has_account
    from .models import DemoCompletionVoid
    check_gate()
    Dealership.objects.select_for_update().get(pk=dealership_id)
    if not Membership.objects.select_for_update().filter(user=actor, user__is_active=True,
            dealership_id=dealership_id, role__in=['owner', 'staff']).exists():
        raise PermissionDenied
    deal = DraftDeal.objects.select_for_update().filter(pk=deal_id, dealership_id=dealership_id).first()
    if deal is None:
        raise Http404
    record = DemoDealCompletion.objects.select_related('packet').filter(deal=deal).first()
    if record is None:
        raise Http404
    review = _void_review(record)
    prior = DemoCompletionVoid.objects.filter(completion=record).first()
    if completion_has_account(deal_id=deal_id):
        raise CompletionChanged('A demo BHPH account is linked. This rehearsal cannot be voided.')
    return record, review, prior


@transaction.atomic
def preview_void(*, dealership_id, deal_id, actor):
    return _void_context(dealership_id, deal_id, actor)


@transaction.atomic
def void_completion(*, dealership_id, deal_id, actor, creation_key, expected_review, reason):
    from .models import DemoCompletionVoid
    record, review, prior = _void_context(dealership_id, deal_id, actor)
    reason = reason.strip()
    if not reason or len(reason) > 1000:
        raise CompletionChanged('Enter a reason of up to 1,000 characters.')
    if review != expected_review:
        raise CompletionChanged('The completion changed since review. Review it again.')
    if prior:
        if (prior.creation_key, prior.actor_id, prior.reason, prior.review_sha256) == (creation_key, actor.pk, reason, review):
            return prior
        raise CompletionChanged('This completion already has a void rehearsal.')
    if DemoCompletionVoid.objects.filter(creation_key=creation_key).exists():
        raise CompletionChanged('This confirmation has already been used.')
    return DemoCompletionVoid.objects.create(completion=record, actor=actor, reason=reason,
        review_sha256=review, creation_key=creation_key)


def _follow_on_money(deal, snapshot, metadata):
    from decimal import Decimal, InvalidOperation
    from .florida_tax import CENT
    from .models import DealType
    from .worksheet import draft_totals
    code = metadata.get('deal_type_code') if isinstance(metadata, dict) else None
    if code not in DealType.values or DealType(code).label != snapshot.get('deal_type') or deal.deal_type != code:
        return DealType.UNDECIDED, {name: Decimal('0.00') for name in MONEY_FIELDS}, {}, False, (
            'The frozen deal type could not be verified. The new draft starts with Deal type Not chosen and $0.00 worksheet amounts for manual entry.')
    worksheet = snapshot.get('worksheet')
    if not isinstance(worksheet, dict):
        return code, {name: Decimal('0.00') for name in MONEY_FIELDS}, {}, False, (
            'Frozen worksheet figures could not be verified as exact nonnegative money. The new draft starts at $0.00 for manual entry.')
    amounts = {}
    for name in MONEY_FIELDS:
        raw = worksheet.get(name)
        if not isinstance(raw, str):
            return code, {k: Decimal('0.00') for k in MONEY_FIELDS}, {}, False, (
                'Frozen worksheet figures could not be verified as exact nonnegative money. The new draft starts at $0.00 for manual entry.')
        try:
            val = Decimal(raw)
        except (InvalidOperation, ValueError, TypeError):
            return code, {k: Decimal('0.00') for k in MONEY_FIELDS}, {}, False, (
                'Frozen worksheet figures could not be verified as exact nonnegative money. The new draft starts at $0.00 for manual entry.')
        if (not val.is_finite() or val < 0 or val > Decimal('9999999999.99')
                or val != val.quantize(CENT) or getattr(deal, name) != val):
            return code, {k: Decimal('0.00') for k in MONEY_FIELDS}, {}, False, (
                'Frozen worksheet figures could not be verified against the source record. The new draft starts at $0.00 for manual entry.')
        amounts[name] = val
    if amounts['trade_allowance'] or amounts['trade_payoff']:
        return code, {k: Decimal('0.00') for k in MONEY_FIELDS}, {}, False, (
            'The original includes a trade adjustment. Trade details are not copied, so all figures start at $0.00 for manual review.')
    if amounts['sale_price'] <= 0 or draft_totals(amounts)['balance'] < 0:
        return code, {k: Decimal('0.00') for k in MONEY_FIELDS}, {}, False, (
            'Frozen worksheet figures do not produce a valid nonnegative balance. The new draft starts at $0.00 for manual entry.')
    tax_context = snapshot.get('tax_context')
    if not isinstance(tax_context, dict) or tax_context != deal.tax_context or tax_context.get('mode') not in (None, 'manual', 'fl'):
        return code, {k: Decimal('0.00') for k in MONEY_FIELDS}, {}, False, (
            'Frozen tax settings could not be verified. The new draft starts at $0.00 with manual tax review.')
    if tax_context.get('mode') == 'fl':
        from .florida_tax import refresh
        probe = DraftDeal(dealership_id=deal.dealership_id, vehicle_id=deal.vehicle_id, buyer_id=deal.buyer_id,
                          co_buyer_id=deal.co_buyer_id, deal_type=code, tax_context=deepcopy(tax_context), **amounts)
        try:
            refresh(probe)
        except ValidationError:
            return code, {k: Decimal('0.00') for k in MONEY_FIELDS}, {}, False, (
                'The frozen Florida tax estimate cannot be recalculated under current settings. The new draft starts at $0.00 so no unverified tax or balance is copied.')
        if probe.tax != amounts['tax'] or probe.tax_context != tax_context:
            return code, {k: Decimal('0.00') for k in MONEY_FIELDS}, {}, False, (
                'The frozen Florida tax estimate no longer matches the recorded inputs. The new draft starts at $0.00 so no stale tax is copied.')
    return code, amounts, deepcopy(tax_context), True, ''


def _follow_on_context(dealership_id, deal_id, actor):
    from customers.models import Customer
    from finance.account_services import completion_has_account
    from .models import DemoCompletionVoid, DemoFollowOnDraft
    check_gate()
    if not getattr(settings, 'DEBUG', False):
        raise Http404
    Dealership.objects.select_for_update().get(pk=dealership_id)
    if not Membership.objects.select_for_update().filter(user=actor, user__is_active=True,
            dealership_id=dealership_id, role__in=['owner', 'staff']).exists():
        raise PermissionDenied
    deal = DraftDeal.objects.select_for_update().filter(pk=deal_id, dealership_id=dealership_id).first()
    if deal is None:
        raise Http404
    record = DemoDealCompletion.objects.select_related('packet').filter(deal=deal).first()
    if record is None:
        raise Http404
    snapshot = verified_snapshot(record)
    if completion_has_account(deal_id=deal_id):
        raise CompletionChanged('A demo BHPH account is linked to this deal. A follow-on draft cannot be created.')
    void_record = DemoCompletionVoid.objects.filter(completion=record).first()
    if void_record is None:
        raise CompletionChanged('Record a void rehearsal before starting a follow-on draft.')
    if void_record.review_sha256 != _void_review(record):
        raise CompletionChanged('The void rehearsal failed its integrity check against the frozen completion.')
    prior = DemoFollowOnDraft.objects.select_related('draft', 'actor').filter(void_rehearsal=void_record).first()
    if prior:
        return {'record': record, 'void_record': void_record, 'snapshot': snapshot, 'prior': prior}
    vehicle_info = snapshot.get('vehicle') if isinstance(snapshot, dict) else None
    buyer_info = snapshot.get('buyer') if isinstance(snapshot, dict) else None
    co_info = snapshot.get('co_buyer') if isinstance(snapshot, dict) else None
    if (not isinstance(vehicle_info, dict) or not isinstance(buyer_info, dict)
            or vehicle_info.get('record_id') != deal.vehicle_id
            or buyer_info.get('record_id') != deal.buyer_id
            or (co_info.get('record_id') if isinstance(co_info, dict) else None) != deal.co_buyer_id):
        raise CompletionChanged('Frozen party or vehicle references do not match the completed deal.')
    vehicle = Vehicle.objects.select_for_update().filter(pk=deal.vehicle_id, dealership_id=dealership_id).first()
    if vehicle is None:
        raise CompletionChanged('The frozen vehicle is not in this dealership.')
    if vehicle.status == Vehicle.Status.SOLD:
        raise CompletionChanged('The frozen vehicle is currently marked sold. Choose an available vehicle on a new deal.')
    customer_ids = [deal.buyer_id] + ([deal.co_buyer_id] if deal.co_buyer_id else [])
    people = {c.pk: c for c in Customer.objects.select_for_update().filter(
        pk__in=customer_ids, dealership_id=dealership_id).order_by('pk')}
    if len(people) != len(set(customer_ids)):
        raise CompletionChanged('The frozen buyer or co-buyer is not in this dealership.')
    deal_type_code, amounts, tax_context, money_copied, money_notice = _follow_on_money(deal, snapshot, record.metadata)
    review_payload = {
        'completion_id': record.pk,
        'void_id': void_record.pk,
        'deal_id': deal.pk,
        'completion_review_sha256': record.review_sha256,
        'void_review_sha256': void_record.review_sha256,
        'vehicle_id': vehicle.pk,
        'buyer_id': deal.buyer_id,
        'co_buyer_id': deal.co_buyer_id,
        'vehicle_revision': vehicle.revision, 'vehicle_status': vehicle.status,
        'buyer_revision': people[deal.buyer_id].revision,
        'co_buyer_revision': people[deal.co_buyer_id].revision if deal.co_buyer_id else None,
        'deal_type': deal_type_code,
        'money_copied': money_copied,
        'amounts': {name: str(amounts[name]) for name in MONEY_FIELDS},
        'tax_context': tax_context,
    }
    review = source_digest(review_payload)
    return {
        'record': record,
        'void_record': void_record,
        'snapshot': snapshot,
        'vehicle': vehicle,
        'buyer': people[deal.buyer_id],
        'co_buyer': people.get(deal.co_buyer_id),
        'deal_type': deal_type_code,
        'amounts': amounts,
        'tax_context': tax_context,
        'money_copied': money_copied,
        'money_notice': money_notice,
        'review_sha256': review,
        'prior': prior,
    }


@transaction.atomic
def preview_follow_on_draft(*, dealership_id, deal_id, actor):
    return _follow_on_context(dealership_id, deal_id, actor)


@transaction.atomic
def create_follow_on_draft(*, dealership_id, deal_id, actor, creation_key, expected_review, reason, confirmed=False):
    from .models import DemoFollowOnDraft
    state = _follow_on_context(dealership_id, deal_id, actor)
    reason = (reason or '').strip()
    if not confirmed:
        raise CompletionChanged('Confirm that this creates a separate synthetic draft before continuing.')
    if not reason or len(reason) > 1000:
        raise CompletionChanged('Enter a reason of up to 1,000 characters.')
    prior = state['prior']
    if prior:
        if (prior.creation_key, prior.actor_id, prior.reason, prior.review_sha256) == (creation_key, actor.pk, reason, expected_review):
            return prior
        raise CompletionChanged(f'A follow-on draft (Deal #{prior.draft_id}) was already created for this voided rehearsal.')
    if state['review_sha256'] != expected_review:
        raise CompletionChanged('The voided completion or linked records changed since review. Review the preview again.')
    if DemoFollowOnDraft.objects.filter(creation_key=creation_key).exists() or DraftDeal.objects.filter(dealership_id=dealership_id, creation_key=creation_key).exists():
        raise CompletionChanged('This confirmation has already been used. Review again before creating a follow-on draft.')
    record = state['record']
    void_record = state['void_record']
    draft = DraftDeal(
        dealership_id=dealership_id,
        creation_key=creation_key,
        vehicle=state['vehicle'],
        buyer=state['buyer'],
        co_buyer=state['co_buyer'],
        deal_type=state['deal_type'],
        tax_context=state['tax_context'],
        notes=(record.metadata.get('deal_notes') or '') if isinstance(record.metadata, dict) else '',
        **state['amounts'],
    )
    draft.full_clean(exclude=['creation_key'])
    draft.save()
    provenance = {
        'source_deal_id': record.deal_id,
        'source_completion_id': record.pk,
        'source_void_id': void_record.pk,
        'source_packet_id': record.packet_id,
        'source_revision': record.source_revision,
        'source_review_sha256': record.review_sha256,
        'void_review_sha256': void_record.review_sha256,
        'follow_on_review_sha256': state['review_sha256'],
        'money_copied': state['money_copied'],
        'money_notice': state['money_notice'],
        'synthetic_only': True,
    }
    follow_on = DemoFollowOnDraft.objects.create(
        void_rehearsal=void_record,
        draft=draft,
        actor=actor,
        reason=reason,
        review_sha256=state['review_sha256'],
        creation_key=creation_key,
    )
    DealEvent.objects.create(
        deal=draft,
        actor=actor,
        snapshot={
            'schema_version': 8,
            'action': 'follow_on_draft_created',
            'revision': draft.revision,
            'reason': reason,
            'deal_type': draft.deal_type,
            'vehicle_id': draft.vehicle_id,
            'buyer_id': draft.buyer_id,
            'co_buyer_id': draft.co_buyer_id,
            'tax_context': draft.tax_context,
            'finance_proposals': {},
            'trades': [],
            'follow_on_provenance': provenance,
            **{name: str(getattr(draft, name)) for name in MONEY_FIELDS},
        },
    )
    return follow_on

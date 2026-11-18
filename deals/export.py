# SPDX-License-Identifier: MPL-2.0
"""Private synthetic deal-module export component; not a dealership backup.

Nine owned record types are included: drafts, financing proposals, trade-ins,
change events, follow-ups, follow-up events and completion rehearsals. Foreign
records are referenced by ID. Completion packet version is included, but document
content, document files, financial ledgers and user records are outside scope.

This is a multi-query transaction, not a repeatable-read snapshot under the
usual PostgreSQL READ COMMITTED isolation level. Concurrent writes may affect
consistency; quiesce writes or use a separately reviewed snapshot mechanism.
The return value includes unredacted free text and must be protected. This
service has no endpoint, encryption, delivery audit, import or restore function.
Callers must authorize and audit delivery independently before exposing data.
"""
import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from core.models import Membership
from .models import (DraftDeal, DraftFinanceProposal, DraftTradeIn, DealEvent,
                     DealFollowUp, FollowUpEvent, DemoDealCompletion, DemoCompletionVoid, DemoFollowOnDraft)

FORMAT_VERSION = 'railet-synthetic-deals-v1'
MAX_DEALS = 10000
MAX_CHILD_ROWS = 100000
MAX_BYTES = 32 * 1024 * 1024


class DealExportError(Exception):
    """No partial export is returned when the capture cannot be trusted."""


def _bounded(query, limit):
    rows = list(query[:limit + 1])
    if len(rows) > limit:
        raise DealExportError('Deal export exceeds its record limit; no partial data returned.')
    return rows


def _value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, dict):
        return {key: _value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_value(item) for item in value]
    return value


def _rows(model, scope, fields, limit=None):
    if limit is None:
        limit = MAX_CHILD_ROWS
    return [_value(row) for row in _bounded(model.objects.filter(**scope).order_by('pk').values(*fields), limit)]


@transaction.atomic
def export_deals(*, dealership_id, actor):
    """Export deal-owned synthetic records for an active owner of one dealership."""
    if not (getattr(settings, 'DEBUG', False) and getattr(settings, 'DEMO_COMPLETION_ENABLED', False)
            and getattr(settings, 'DEMO_PACKETS_ENABLED', False)):
        raise PermissionDenied('Synthetic deal export is disabled.')
    if not getattr(actor, 'is_authenticated', False) or not getattr(actor, 'pk', None):
        raise PermissionDenied
    membership = Membership.objects.select_for_update().filter(
        user_id=actor.pk, user__is_active=True, dealership_id=dealership_id, role=Membership.Role.OWNER).first()
    if membership is None:
        raise PermissionDenied
    started = timezone.now()
    scoped = DraftDeal.objects.filter(dealership_id=dealership_id)
    if scoped.exclude(Q(vehicle__dealership_id=dealership_id) & Q(buyer__dealership_id=dealership_id)
                      & (Q(co_buyer__isnull=True) | Q(co_buyer__dealership_id=dealership_id))).exists():
        raise DealExportError('A deal has an out-of-scope party or vehicle reference; no export prepared.')
    if DraftTradeIn.objects.filter(deal__dealership_id=dealership_id, inventory_vehicle__isnull=False).exclude(
            inventory_vehicle__dealership_id=dealership_id).exists():
        raise DealExportError('A trade has an out-of-scope inventory reference; no export prepared.')
    deals = _rows(DraftDeal, {'dealership_id': dealership_id}, (
        'id', 'dealership_id', 'creation_key', 'vehicle_id', 'buyer_id', 'co_buyer_id', 'deal_type',
        'sale_price', 'tax', 'title_registration', 'dealer_fee', 'trade_allowance', 'trade_payoff',
        'down_payment', 'tax_context', 'notes', 'revision', 'created_at', 'updated_at',
        'archived_at', 'archived_by_id', 'archive_reason'), MAX_DEALS)
    scope = {'deal__dealership_id': dealership_id}
    proposals = _rows(DraftFinanceProposal, scope, ('id', 'deal_id', 'kind', 'interest_method', 'creditor_name',
        'payment_frequency', 'payment_count', 'annual_contract_rate', 'illustration_finance_charge', 'first_payment_date', 'updated_at'))
    trades = _rows(DraftTradeIn, scope, ('id', 'deal_id', 'vin', 'year', 'make', 'model', 'title_brand',
        'odometer_reading', 'odometer_unit', 'odometer_status', 'lienholder_name', 'payoff_good_through',
        'notes', 'inventory_vehicle_id', 'archived_at', 'created_at', 'updated_at'))
    events = _rows(DealEvent, scope, ('id', 'deal_id', 'actor_id', 'snapshot', 'created_at'))
    followups = _rows(DealFollowUp, scope, ('id', 'deal_id', 'title', 'detail', 'assigned_to_id', 'due_on',
        'completed_at', 'completed_by_id', 'created_by_id', 'creation_key', 'revision', 'created_at', 'updated_at'))
    followup_events = _rows(FollowUpEvent, {'follow_up__deal__dealership_id': dealership_id},
        ('id', 'follow_up_id', 'actor_id', 'action', 'snapshot', 'created_at'))
    completions = _rows(DemoDealCompletion, scope, ('id', 'deal_id', 'packet_id', 'source_revision',
        'source_sha256', 'artifact_sha256', 'review_sha256', 'metadata', 'review_notes', 'creation_key',
        'actor_id', 'created_at', 'policy_version', 'packet__deal_id', 'packet__template_version'))
    if any(row['packet__deal_id'] != row['deal_id'] for row in completions):
        raise DealExportError('A completion references a different deal packet; no export prepared.')
    for row in completions:
        row['packet_template_version'] = row.pop('packet__template_version')
        row.pop('packet__deal_id')
    voids = _rows(DemoCompletionVoid, {'completion__deal__dealership_id': dealership_id},
        ('id', 'completion_id', 'actor_id', 'reason', 'review_sha256', 'creation_key', 'created_at', 'policy_version'))
    follow_on = _rows(DemoFollowOnDraft, {'void_rehearsal__completion__deal__dealership_id': dealership_id},
        ('id', 'void_rehearsal_id', 'draft_id', 'actor_id', 'reason', 'review_sha256', 'creation_key', 'created_at', 'policy_version', 'draft__dealership_id'))
    if any(row.pop('draft__dealership_id') != dealership_id for row in follow_on):
        raise DealExportError('Follow-on draft has an out-of-scope reference; no export prepared.')
    data = {'format': FORMAT_VERSION, 'synthetic_only': True, 'dealership_id': dealership_id,
        'exported_by_user_id': actor.pk, 'capture_started_at': started.isoformat(),
        'capture_finished_at': timezone.now().isoformat(),
        'consistency': 'Multiple queries in one transaction; not guaranteed to represent a single point in time.',
        'scope': 'Deal-owned records and histories only; document bytes and complete dealership recovery are excluded.',
        'deals': deals, 'finance_proposals': proposals, 'trades': trades, 'deal_events': events,
        'follow_ups': followups, 'follow_up_events': followup_events, 'completions': completions, 'completion_void_rehearsals': voids, 'follow_on_drafts': follow_on}
    try:
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    except (TypeError, ValueError) as error:
        raise DealExportError('Stored deal data cannot be encoded as valid JSON; no export prepared.') from error
    if len(payload) > MAX_BYTES:
        raise DealExportError('Deal export exceeds its size limit; no partial data returned.')
    return data

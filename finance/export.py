# SPDX-License-Identifier: MPL-2.0
"""Private synthetic finance-module export; not a complete backup or statement.

Includes books, postings, schedules, frozen account contexts, servicing plans,
export events, and their stored versions and actor IDs. Deal, customer, document,
user and provider records are references only and are not exported here. Prior
export events have hashes, not retained copies of previously downloaded archives.

Several scoped database queries share a transaction but are not guaranteed to
observe one point in time under PostgreSQL READ COMMITTED. Quiesce writers or use
a separately reviewed coordinated snapshot for consistent exports. The result
contains private unredacted text, is not encrypted, and this internal service
provides no endpoint, delivery audit, import or restore. A caller must implement
its own authorization, secure delivery and audit before exposing any data.
"""
import json
from datetime import date, datetime
from uuid import UUID
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from core.models import Membership
from .models import (DemoBook, DemoPosting, DemoSchedule, DemoAccountContext,
                     DemoAccountExport, DemoServicingPlan)
from .schedule_services import result_digest

FORMAT_VERSION = 'railet-synthetic-finance-v1'
MAX_BOOKS = 10000
MAX_CHILD_ROWS = 100000
MAX_BYTES = 32 * 1024 * 1024


class FinanceExportError(Exception):
    """A bounded, scoped or integrity check failed; return no partial export."""


def _records(query, limit):
    rows = list(query.order_by('pk')[:limit + 1])
    if len(rows) > limit:
        raise FinanceExportError('Finance export exceeds its record limit; no data returned.')
    return rows


def _convert(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _convert(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_convert(item) for item in value]
    return value


def _metadata(record):
    return {field.attname: _convert(getattr(record, field.attname)) for field in record._meta.concrete_fields}


def _verify_journal(books, postings):
    grouped = {book.pk: [] for book in books}
    by_id = {posting.pk: posting for posting in postings}
    for posting in postings:
        grouped[posting.book_id].append(posting)
        if (posting.amount_cents <= 0 or posting.effective_on < posting.book.opening_on
                or posting.payment_method not in ('unspecified', 'cash', 'check', 'other')
                or (posting.kind == 'opening' and posting.payment_method != 'unspecified')):
            raise FinanceExportError('A posting has invalid amount or effective date; no data returned.')
        if posting.kind == 'reversal':
            original = by_id.get(posting.reverses_id)
            if (original is None or original.kind != 'receipt' or original.book_id != posting.book_id
                or original.amount_cents != posting.amount_cents or original.payment_method != posting.payment_method
                or posting.effective_on < original.effective_on):
                raise FinanceExportError('A reversal does not match its original receipt; no data returned.')
    allowed_pairs = {'opening': ('principal', 'opening_offset'), 'receipt': ('cash_control', 'unapplied'),
                     'reversal': ('unapplied', 'cash_control')}
    for book in books:
        entries = grouped[book.pk]
        if sum(entry.kind == 'opening' for entry in entries) != 1:
            raise FinanceExportError('An account does not have exactly one opening; no data returned.')
        for entry in entries:
            if (entry.debit, entry.credit) != allowed_pairs.get(entry.kind):
                raise FinanceExportError('A posting has an invalid debit or credit; no data returned.')


@transaction.atomic
def export_finance(*, dealership_id, actor):
    """Return bounded JSON-compatible synthetic finance records to a scoped owner."""
    if not all(getattr(settings, flag, False) for flag in ('DEBUG', 'DEMO_LEDGER_ENABLED', 'DEMO_SERVICING_ENABLED')):
        raise PermissionDenied('Synthetic finance export is disabled.')
    if not getattr(actor, 'is_authenticated', False) or not getattr(actor, 'pk', None):
        raise PermissionDenied
    if not Membership.objects.select_for_update().filter(user_id=actor.pk, user__is_active=True,
            dealership_id=dealership_id, role=Membership.Role.OWNER).exists():
        raise PermissionDenied
    started = timezone.now()
    if DemoBook.objects.filter(dealership_id=dealership_id).exclude(customer__dealership_id=dealership_id).exists():
        raise FinanceExportError('An account references a customer from another dealership; no data returned.')
    scope = {'book__dealership_id': dealership_id}
    if DemoAccountContext.objects.filter(**scope).exclude(
            deal__dealership_id=dealership_id, deal__buyer_id=F('book__customer_id'),
            deal__vehicle__dealership_id=dealership_id).exists():
        raise FinanceExportError('An account context references an out-of-scope deal; no data returned.')
    if DemoServicingPlan.objects.filter(**scope).exclude(schedule__book_id=F('book_id')).exists():
        raise FinanceExportError('A servicing plan references a different account schedule; no data returned.')
    books = _records(DemoBook.objects.filter(dealership_id=dealership_id), MAX_BOOKS)
    postings = _records(DemoPosting.objects.filter(**scope).select_related('book'), MAX_CHILD_ROWS)
    schedules = _records(DemoSchedule.objects.filter(**scope), MAX_CHILD_ROWS)
    contexts = _records(DemoAccountContext.objects.filter(**scope), MAX_CHILD_ROWS)
    plans = _records(DemoServicingPlan.objects.filter(**scope), MAX_CHILD_ROWS)
    events = _records(DemoAccountExport.objects.filter(**scope), MAX_CHILD_ROWS)
    _verify_journal(books, postings)
    schedule_by_id = {record.pk: record for record in schedules}
    for schedule in schedules:
        if result_digest(schedule.result) != schedule.result_sha256:
            raise FinanceExportError('A saved schedule failed its integrity check; no data returned.')
    for record in contexts:
        if result_digest(record.snapshot) != record.snapshot_sha256:
            raise FinanceExportError('A saved account context failed its integrity check; no data returned.')
    for plan in plans:
        schedule = schedule_by_id.get(plan.schedule_id)
        if schedule is None or schedule.book_id != plan.book_id or schedule.result_sha256 != plan.schedule_sha256:
            raise FinanceExportError('A servicing baseline does not match its saved schedule; no data returned.')
    data = {'format': FORMAT_VERSION, 'synthetic_only': True, 'dealership_id': dealership_id,
        'exported_by_user_id': actor.pk, 'capture_started_at': started.isoformat(),
        'capture_finished_at': timezone.now().isoformat(),
        'consistency': 'Multiple queries in one transaction; not guaranteed to represent a single point in time.',
        'scope': 'Finance-owned synthetic records only; not a complete dealership backup or live financial statement.',
        'books': [_metadata(record) for record in books], 'postings': [_metadata(record) for record in postings],
        'schedules': [_metadata(record) for record in schedules], 'contexts': [_metadata(record) for record in contexts],
        'servicing_plans': [_metadata(record) for record in plans], 'export_events': [_metadata(record) for record in events]}
    try:
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    except (ValueError, TypeError) as error:
        raise FinanceExportError('Finance metadata cannot be encoded as valid JSON; no data returned.') from error
    if len(payload) > MAX_BYTES:
        raise FinanceExportError('Finance export exceeds its size limit; no data returned.')
    return data

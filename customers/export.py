# SPDX-License-Identifier: MPL-2.0
"""Internal synthetic customer export; not a complete backup or restore format.

This service does not itself write files, encrypt data, or audit delivery.
The private download workflow records preparation of its response.
The queries run in one transaction but do not establish a repeatable-read
snapshot: concurrent writes can appear between queries on PostgreSQL READ
COMMITTED (or fail on SQLite). Quiesce writes or provide a separately reviewed
snapshot mechanism before relying on cross-record consistency. Actor IDs are
provenance references, not exported user records; free-text values are unredacted.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from core.models import Dealership, Membership
from .models import Customer, CustomerActivity, CustomerEvent, CustomerExportEvent, MockMessageSubmission, MockMessageEvent

FORMAT_VERSION = 'railet-synthetic-customers-v3'
MAX_CUSTOMERS = 10000
MAX_ACTIVITIES = 100000
MAX_EVENTS = 100000
MAX_EXPORT_EVENTS = 10000
MAX_MOCK_SUBMISSIONS = 10000
MAX_MOCK_EVENTS = 100000


class CustomerExportTooLarge(Exception):
    """Refuse partial exports when this internal component's limits are exceeded."""


def _bounded(query, maximum):
    records = list(query[:maximum + 1])
    if len(records) > maximum:
        raise CustomerExportTooLarge('Customer export exceeds its limit; no partial data returned.')
    return records


def _iso(value):
    return value.isoformat() if value is not None else None


def authorize_customer_export(*, dealership_id, actor):
    """Call inside an atomic block; lock dealership, then recheck active owner."""
    if not (getattr(settings, 'DEBUG', False) and getattr(settings, 'CUSTOMER_ACTIVITY_DEMO_ENABLED', False)):
        raise PermissionDenied('Synthetic customer export is disabled.')
    if not getattr(actor, 'is_authenticated', False) or not getattr(actor, 'pk', None):
        raise PermissionDenied
    if not Dealership.objects.select_for_update().filter(pk=dealership_id).exists():
        raise PermissionDenied
    membership = Membership.objects.select_for_update().filter(
        user_id=actor.pk, user__is_active=True, dealership_id=dealership_id, role=Membership.Role.OWNER,
    ).first()
    if membership is None:
        raise PermissionDenied
    return membership


@transaction.atomic
def export_customers(*, dealership_id, actor):
    """Return JSON-compatible records for an active dealership owner only.

    The caller must explicitly enable both local development and synthetic
    customer activity. This is a read-only module component and cannot prove that
    the stored data is synthetic. No all-dealership mode is provided.
    """
    authorize_customer_export(dealership_id=dealership_id, actor=actor)
    started = timezone.now()
    # Scope each query independently through the customer; no caller-supplied IDs.
    customers = _bounded(Customer.objects.filter(dealership_id=dealership_id).order_by('pk').values(
        'id', 'dealership_id', 'first_name', 'last_name', 'phone', 'email', 'lead_stage',
        'address_line1', 'address_line2', 'city', 'region', 'postal_code', 'country',
        'phone_normalized', 'email_normalized', 'revision', 'created_at', 'updated_at'), MAX_CUSTOMERS)
    activities = _bounded(CustomerActivity.objects.filter(customer__dealership_id=dealership_id).order_by('pk').values(
        'id', 'customer_id', 'kind', 'detail', 'due_at', 'completed_at', 'created_by_id',
        'completed_by_id', 'assigned_to_id', 'revision', 'creation_key', 'created_at'), MAX_ACTIVITIES)
    events = _bounded(CustomerEvent.objects.filter(customer__dealership_id=dealership_id).order_by('pk').values(
        'id', 'customer_id', 'actor_id', 'changes', 'created_at'), MAX_EVENTS)
    export_events = _bounded(CustomerExportEvent.objects.filter(dealership_id=dealership_id).order_by('pk').values(
        'id', 'dealership_id', 'actor_id', 'created_at', 'format_version', 'sha256', 'byte_size'), MAX_EXPORT_EVENTS)
    # Retained simulator history remains exportable after its optional gate closes.
    mock_submissions = _bounded(MockMessageSubmission.objects.filter(dealership_id=dealership_id).order_by('pk').values(
        'id', 'dealership_id', 'actor_id', 'submission_id', 'recipient_label', 'scenario', 'created_at'), MAX_MOCK_SUBMISSIONS)
    mock_events = _bounded(MockMessageEvent.objects.filter(submission__dealership_id=dealership_id).order_by('pk').values(
        'id', 'submission_id', 'event_id', 'actor_id', 'label', 'created_at'), MAX_MOCK_EVENTS)
    for record in customers:
        record['created_at'] = _iso(record['created_at'])
        record['updated_at'] = _iso(record['updated_at'])
    for record in activities:
        for field in ('due_at', 'completed_at', 'created_at'):
            record[field] = _iso(record[field])
        record['creation_key'] = str(record['creation_key'])
    for record in events:
        record['created_at'] = _iso(record['created_at'])
    for record in export_events:
        record['created_at'] = _iso(record['created_at'])
    for record in mock_submissions:
        record['submission_id'] = str(record['submission_id'])
        record['created_at'] = _iso(record['created_at'])
    for record in mock_events:
        record['event_id'] = str(record['event_id'])
        record['created_at'] = _iso(record['created_at'])
    return {
        'format': FORMAT_VERSION,
        'synthetic_only': True,
        'dealership_id': dealership_id,
        'exported_by_user_id': actor.pk,
        'capture_started_at': _iso(started),
        'capture_finished_at': _iso(timezone.now()),
        'consistency': 'Multiple queries in one transaction; not guaranteed to represent a single point in time.',
        'scope': 'Customer records, customer activities, customer change events, prior customer export-preparation events, and offline mock message simulator history only; simulator labels are not real delivery or consent evidence. The current customer download event is recorded after preparation and is not included. Not a complete backup.',
        'customers': customers,
        'activities': activities,
        'events': events,
        'customer_export_events': export_events,
        'mock_message_submissions': mock_submissions,
        'mock_message_events': mock_events,
    }

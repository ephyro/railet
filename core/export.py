# SPDX-License-Identifier: MPL-2.0
"""Internal synthetic foundation export; not a complete backup or restore format.

This service exports the scoped Dealership, current Membership records with
non-secret user identity provenance, and prior dealership export-preparation
audit events.
It never exports password hashes, session keys, tokens, secret settings, email
addresses, personal `SavedView` preferences, or other dealerships' data.
"""
import json
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from .models import Dealership, DealershipExportEvent, Membership

FORMAT_VERSION = 'railet-synthetic-foundation-v2'
MAX_MEMBERSHIPS = 5000
MAX_EXPORT_EVENTS = 10000
MAX_JSON_BYTES = 4 * 1024 * 1024


class FoundationExportTooLarge(Exception):
    """Refuse partial exports when membership count or serialized byte limits are exceeded."""


def _bounded(query, maximum):
    records = list(query[:maximum + 1])
    if len(records) > maximum:
        raise FoundationExportTooLarge('Foundation export exceeds its record limit; no partial data returned.')
    return records


def _iso(value):
    return value.isoformat() if value is not None else None


def authorize_foundation_export(*, dealership_id, actor):
    """Call inside an atomic block; lock dealership and recheck active owner membership."""
    if not getattr(settings, 'DEBUG', False):
        raise PermissionDenied('Synthetic foundation export is disabled.')
    if not getattr(actor, 'is_authenticated', False) or not getattr(actor, 'pk', None):
        raise PermissionDenied
    # All dealership-package callers lock the dealership before the owner rows,
    # matching follow-up writes and preventing a dealership/membership cycle.
    dealership = Dealership.objects.select_for_update().filter(pk=dealership_id).first()
    if dealership is None:
        raise PermissionDenied
    membership = Membership.objects.select_for_update().filter(
        user_id=actor.pk, user__is_active=True, dealership_id=dealership_id, role=Membership.Role.OWNER,
    ).first()
    if membership is None:
        raise PermissionDenied
    return dealership


@transaction.atomic
def export_foundation(*, dealership_id, actor):
    """Return JSON-compatible dealership identity and member provenance for an active owner.

    Includes the scoped `Dealership`, current `Membership` records with
    allowlisted non-secret user identity references (`user_id`, `username`,
    `is_active`), and prior dealership export-preparation events. Excludes
    passwords, sessions, tokens, secrets, personal saved
    views, vehicle audit events (exported by the inventory module), and other
    modules. Not a complete dealership backup or restore bundle.
    """
    dealership = authorize_foundation_export(dealership_id=dealership_id, actor=actor)
    started = timezone.now()

    raw_memberships = _bounded(
        Membership.objects.filter(dealership_id=dealership_id).select_related('user').order_by('pk'),
        MAX_MEMBERSHIPS,
    )
    memberships = [
        {
            'id': m.pk,
            'dealership_id': m.dealership_id,
            'role': m.role,
            'user_id': m.user_id,
            'username': m.user.get_username(),
            'user_is_active': bool(m.user.is_active),
        }
        for m in raw_memberships
    ]
    export_events = _bounded(
        DealershipExportEvent.objects.filter(dealership_id=dealership_id).order_by('pk').values(
            'id', 'dealership_id', 'actor_id', 'created_at', 'format_version', 'sha256', 'byte_size'
        ), MAX_EXPORT_EVENTS,
    )
    for event in export_events:
        event['created_at'] = _iso(event['created_at'])

    result = {
        'format': FORMAT_VERSION,
        'synthetic_only': True,
        'dealership_id': dealership.pk,
        'exported_by_user_id': actor.pk,
        'capture_started_at': _iso(started),
        'capture_finished_at': _iso(timezone.now()),
        'consistency': (
            'Queries run in one transaction after locking the dealership and owner membership rows; '
            'not a repeatable-read cross-module snapshot.'
        ),
        'scope': (
            'Dealership identity, current membership provenance and prior dealership export-preparation '
            'audit events. The current package event is recorded after preparation and is not included. '
            'User credentials, password hashes, sessions, tokens, '
            'secret settings, personal saved views, and other modules are excluded. Not a complete '
            'dealership backup or restore bundle.'
        ),
        'dealership': {
            'id': dealership.pk,
            'name': dealership.name,
        },
        'memberships': memberships,
        'dealership_export_events': export_events,
    }
    encoded_bytes = len(json.dumps(result, ensure_ascii=False).encode('utf-8'))
    if encoded_bytes > MAX_JSON_BYTES:
        raise FoundationExportTooLarge('Foundation export exceeds its byte size limit; no partial data returned.')
    return result

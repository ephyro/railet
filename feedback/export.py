# SPDX-License-Identifier: MPL-2.0
"""Internal synthetic feedback export; not a complete backup or restore format.

This service does not itself write files, encrypt data, redact free-text fields,
expose an HTTP endpoint, or record a delivery audit event. Queries run in one
transaction after locking the dealership and active owner membership rows.
Author IDs are provenance references, not exported user records; submitted
free-text fields (`subject`, `expected`, `actual`) are unredacted as stored.
"""
import json
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from core.models import Dealership, Membership
from .models import FeedbackReport

FORMAT_VERSION = 'railet-synthetic-feedback-v1'
MAX_REPORTS = 10000
MAX_JSON_BYTES = 16 * 1024 * 1024


class FeedbackExportTooLarge(Exception):
    """Refuse partial exports when record or serialized byte limits are exceeded."""


def _bounded(query, maximum):
    records = list(query[:maximum + 1])
    if len(records) > maximum:
        raise FeedbackExportTooLarge('Feedback export exceeds its record limit; no partial data returned.')
    return records


def _iso(value):
    return value.isoformat() if value is not None else None


def authorize_feedback_export(*, dealership_id, actor):
    """Call inside an atomic block; lock dealership and recheck active owner membership."""
    if not getattr(settings, 'DEBUG', False):
        raise PermissionDenied('Synthetic feedback export is disabled.')
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
def export_feedback(*, dealership_id, actor):
    """Return JSON-compatible feedback reports for an active dealership owner only.

    Includes all dealership feedback reports (authored by owners, staff, or
    viewers) ordered by primary key. Free-text fields are unredacted. No HTTP
    endpoint or delivery audit event is provided by this module component.
    """
    authorize_feedback_export(dealership_id=dealership_id, actor=actor)
    started = timezone.now()
    reports = _bounded(
        FeedbackReport.objects.filter(dealership_id=dealership_id).order_by('pk').values(
            'id', 'dealership_id', 'author_id', 'submission_key',
            'kind', 'area', 'subject', 'expected', 'actual', 'created_at',
        ),
        MAX_REPORTS,
    )
    for record in reports:
        record['submission_key'] = str(record['submission_key'])
        record['created_at'] = _iso(record['created_at'])

    result = {
        'format': FORMAT_VERSION,
        'synthetic_only': True,
        'unredacted_free_text': True,
        'delivery_audited': False,
        'dealership_id': dealership_id,
        'exported_by_user_id': actor.pk,
        'capture_started_at': _iso(started),
        'capture_finished_at': _iso(timezone.now()),
        'consistency': 'Single-table query in one transaction after locking dealership and owner membership rows.',
        'scope': (
            'Dealership feedback reports only (`subject`, `expected`, and `actual` free text are unredacted; '
            'author IDs are provenance references, not user profiles). This internal component has no '
            'HTTP endpoint or delivery audit event and is not a complete dealership backup or restore bundle.'
        ),
        'reports': reports,
    }
    encoded_bytes = len(json.dumps(result, ensure_ascii=False).encode('utf-8'))
    if encoded_bytes > MAX_JSON_BYTES:
        raise FeedbackExportTooLarge('Feedback export exceeds its byte size limit; no partial data returned.')
    return result

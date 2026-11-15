# SPDX-License-Identifier: MPL-2.0
"""Offline-only message delivery simulator, unrelated to provider semantics.

No phone number, real recipient, message text, customer record, financial data,
consent, network request or callback is accepted. Fixed labels are a local
simulation, not delivery or consent evidence. Both development mode and an
explicit DEMO_MESSAGE_SIMULATOR_ENABLED setting (default absent/false) must be
set, together with the existing customer activity demo gate. IDs are UUIDs.

Delivery observations may arrive in any order. The projection uses the set of
retained observations: delivered or failed dominates accepted; simultaneous
terminal labels produce 'mock-conflict'. No event is discarded or overwritten.
An event ID is unique per submission; submission IDs are dealership-scoped.
Retries require identical actor and facts. PostgreSQL row locks serialize
concurrent submissions/events; SQLite does not supply row-level locking and
concurrent writers may fail with a database-locked error and must retry.
"""
from uuid import UUID
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from core.models import Dealership, Membership
from .models import MockMessageEvent, MockMessageSubmission

RECIPIENTS = frozenset(('mock-recipient-alpha', 'mock-recipient-beta'))
SCENARIOS = frozenset(('mock-follow-up', 'mock-appointment'))
EVENTS = frozenset(('mock-accepted', 'mock-delivered', 'mock-failed'))


class SimulatorConflict(ValidationError):
    """A local ID has already been used with different immutable facts."""


def _authorize(*, dealership_id, actor):
    if not (getattr(settings, 'DEBUG', False) and getattr(settings, 'CUSTOMER_ACTIVITY_DEMO_ENABLED', False)
            and getattr(settings, 'DEMO_MESSAGE_SIMULATOR_ENABLED', False)):
        raise PermissionDenied('Offline message simulator is disabled.')
    if not getattr(actor, 'is_authenticated', False) or not getattr(actor, 'pk', None):
        raise PermissionDenied
    if not Membership.objects.select_for_update().filter(user_id=actor.pk, user__is_active=True,
            dealership_id=dealership_id, role__in=(Membership.Role.OWNER, Membership.Role.STAFF)).exists():
        raise PermissionDenied


def _uuid(value):
    if not isinstance(value, UUID):
        raise ValidationError('Use a UUID for the invented simulator identifier.')
    return value


@transaction.atomic
def submit_mock(*, dealership_id, actor, submission_id, recipient_label, scenario):
    """Create or retry an invented submission; no customer lookup occurs."""
    _authorize(dealership_id=dealership_id, actor=actor)
    _uuid(submission_id)
    if recipient_label not in RECIPIENTS or scenario not in SCENARIOS:
        raise ValidationError('Choose fixed mock recipient and scenario labels.')
    Dealership.objects.select_for_update().get(pk=dealership_id)
    prior = MockMessageSubmission.objects.filter(dealership_id=dealership_id, submission_id=submission_id).first()
    if prior:
        if (prior.actor_id, prior.recipient_label, prior.scenario) != (actor.pk, recipient_label, scenario):
            raise SimulatorConflict('Submission ID already has different facts.')
        return prior, False
    return MockMessageSubmission.objects.create(dealership_id=dealership_id, actor=actor,
        submission_id=submission_id, recipient_label=recipient_label, scenario=scenario), True


@transaction.atomic
def record_mock_event(*, dealership_id, actor, submission_id, event_id, label):
    """Append an invented event; repeated IDs cannot change immutable facts."""
    _authorize(dealership_id=dealership_id, actor=actor)
    _uuid(submission_id); _uuid(event_id)
    if label not in EVENTS:
        raise ValidationError('Choose a fixed mock event label.')
    submission = get_object_or_404(MockMessageSubmission.objects.select_for_update(),
                                   dealership_id=dealership_id, submission_id=submission_id)
    prior = submission.events.filter(event_id=event_id).first()
    if prior:
        if (prior.actor_id, prior.label) != (actor.pk, label):
            raise SimulatorConflict('Event ID already has different facts.')
        return prior, False
    return MockMessageEvent.objects.create(submission=submission, actor=actor, event_id=event_id, label=label), True


@transaction.atomic
def mock_status(*, dealership_id, actor, submission_id):
    """Return an order-independent local label; never a real delivery status."""
    _authorize(dealership_id=dealership_id, actor=actor)
    _uuid(submission_id)
    submission = get_object_or_404(MockMessageSubmission.objects, dealership_id=dealership_id, submission_id=submission_id)
    labels = set(submission.events.values_list('label', flat=True))
    if {'mock-delivered', 'mock-failed'} <= labels:
        return 'mock-conflict'
    if 'mock-delivered' in labels:
        return 'mock-delivered'
    if 'mock-failed' in labels:
        return 'mock-failed'
    return 'mock-accepted' if 'mock-accepted' in labels else 'mock-submitted'

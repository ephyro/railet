# SPDX-License-Identifier: MPL-2.0
"""Offline, invented-data-only preservation decision rehearsal; no disposal authority."""
from dataclasses import dataclass
from enum import Enum
import re


class State(str, Enum):
    PROVISIONAL = 'provisional'
    CONFIRMED = 'confirmed'
    RELEASE_REQUESTED = 'release_requested'
    RELEASED = 'released'


_TRANSITIONS = {
    (State.PROVISIONAL, 'confirm'): State.CONFIRMED,
    (State.PROVISIONAL, 'request_release'): State.RELEASE_REQUESTED,
    (State.CONFIRMED, 'request_release'): State.RELEASE_REQUESTED,
    (State.RELEASE_REQUESTED, 'approve_release'): State.RELEASED,
    (State.RELEASED, 'reactivate'): State.PROVISIONAL,
}


@dataclass(frozen=True)
class Event:
    action: str
    actor: str
    before: State | None
    after: State
    requester: str | None = None
    prior_release_event: int | None = None


@dataclass(frozen=True)
class Hold:
    identifier: str
    state: State
    records: frozenset[str]
    scope_unknown: bool
    events: tuple[Event, ...]


@dataclass(frozen=True)
class Decision:
    blocked_by: tuple[str, ...]
    unknown_scope: tuple[str, ...]

    @property
    def hold_clear_for_review(self):
        """Only a hold check; never a determination of disposal eligibility."""
        return not self.blocked_by and not self.unknown_scope


_ID = re.compile(r'synthetic:[a-z0-9][a-z0-9_-]{0,63}\Z')


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError('Use a synthetic: identifier containing lowercase letters, numbers, _ or -.')
    return value


def _gate(enabled):
    if enabled is not True:
        raise PermissionError('Synthetic rehearsal requires explicit enablement.')


def _validate_hold(hold):
    """Validate structural consistency, not authenticity or authorization."""
    if type(hold) is not Hold:
        raise ValueError('A rehearsal hold is required.')
    _id(hold.identifier)
    if (type(hold.state) is not State or type(hold.scope_unknown) is not bool
            or type(hold.records) is not frozenset or type(hold.events) is not tuple
            or not hold.events):
        raise ValueError('Hold state, scope and history must be immutable and complete.')
    for record in hold.records:
        _id(record)
    previous = None
    for index, event in enumerate(hold.events):
        if type(event) is not Event or type(event.action) is not str:
            raise ValueError('Hold history must contain rehearsal events.')
        _id(event.actor)
        if index == 0:
            if (event.action != 'placed' or event.before is not None
                    or event.after is not State.PROVISIONAL
                    or event.requester is not None or event.prior_release_event is not None):
                raise ValueError('Hold history must begin with a placement.')
            previous = State.PROVISIONAL
            continue
        if event.before is not previous:
            raise ValueError('Hold history has an inconsistent transition.')
        target = _TRANSITIONS.get((previous, event.action))
        if target is None or event.after is not target:
            raise ValueError('Hold history has an invalid transition.')
        if event.action == 'approve_release':
            requester = hold.events[index - 1].actor
            if type(event.requester) is not str or event.requester != requester or event.actor == requester:
                raise ValueError('Release approval requires a different actor and matching requester.')
        elif event.requester is not None:
            raise ValueError('Unexpected release requester.')
        if event.action == 'reactivate':
            if type(event.prior_release_event) is not int or event.prior_release_event != index - 1:
                raise ValueError('Reactivation must link the immediately preceding release.')
        elif event.prior_release_event is not None:
            raise ValueError('Unexpected prior release reference.')
        previous = target
    if hold.state is not previous:
        raise ValueError('Hold state does not match its history.')


def place(identifier, actor, records=(), *, scope_unknown, enabled=False):
    _gate(enabled)
    _id(identifier); _id(actor)
    if not isinstance(scope_unknown, bool):
        raise ValueError('Scope must be explicitly known or unknown.')
    if isinstance(records, (str, bytes)):
        raise ValueError('Records must be a collection of synthetic identifiers.')
    items = frozenset(_id(record) for record in records)
    event = Event('placed', actor, None, State.PROVISIONAL)
    return Hold(identifier, State.PROVISIONAL, items, scope_unknown, (event,))


def transition(hold, action, actor, *, enabled=False):
    _gate(enabled); _id(actor)
    _validate_hold(hold)
    if type(action) is not str:
        raise ValueError('Invalid hold transition.')
    target = _TRANSITIONS.get((hold.state, action))
    if target is None:
        raise ValueError('Invalid hold transition.')
    requester = hold.events[-1].actor if action == 'approve_release' else None
    if requester == actor:
        raise ValueError('Release approver must differ from requester.')
    release_index = len(hold.events) - 1 if action == 'reactivate' else None
    event = Event(action, actor, hold.state, target, requester, release_index)
    return Hold(hold.identifier, target, hold.records, hold.scope_unknown, hold.events + (event,))


def assess(record, holds, *, enabled=False):
    _gate(enabled); _id(record)
    holds = tuple(holds)
    for hold in holds:
        _validate_hold(hold)
    if len({hold.identifier for hold in holds}) != len(holds):
        raise ValueError('Hold identifiers must be unique.')
    active = [hold for hold in holds if hold.state != State.RELEASED]
    return Decision(tuple(sorted(h.identifier for h in active if record in h.records)),
                    tuple(sorted(h.identifier for h in active if h.scope_unknown)))

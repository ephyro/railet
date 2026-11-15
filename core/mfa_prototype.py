# SPDX-License-Identifier: MPL-2.0
"""Local synthetic TOTP experiment. Never use for login or real identities."""
import os
import re
from hmac import compare_digest
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django_otp.oath import TOTP

from . import mfa_secrets
from .models import SyntheticMFAEvent, SyntheticMFAFactor

_CODE = re.compile(r'[0-9]{6}\Z', re.ASCII)
_PREFIX = b'synthetic:'
_SEED_BYTES = 20
_FAILURES = 5
_LOCK_SECONDS = 60
_MAX_COLLISION_SCAN = 128
_ENROLLMENT = 'enrolled-v2'


def _last_continuous_match(totp, code):
    """Consume matching steps whose skew windows touch, without storing codes."""
    last_match = totp.t()
    totp.drift = 0
    candidate = last_match + 1
    checked = 0
    # With one-step tolerance, validity windows touch for matches at most
    # three steps apart. Extend the scan if another match extends the window.
    while candidate <= last_match + 3:
        if checked >= _MAX_COLLISION_SCAN:
            return None
        totp.time = candidate * totp.step
        if compare_digest(f'{totp.token():06d}', code):
            last_match = candidate
        candidate += 1
        checked += 1
    return last_match


def enroll(*, dealership, user, factor):
    """Create an isolated fake factor; no seed is returned or displayed."""
    context = {'dealership': dealership, 'user': user, 'factor': factor}
    envelope = mfa_secrets.encrypt_synthetic_secret(_PREFIX + os.urandom(_SEED_BYTES), **context)
    with transaction.atomic():
        item = SyntheticMFAFactor.objects.create(
            dealership_ref=dealership, user_ref=user, factor_ref=factor, secret_envelope=envelope,
        )
        SyntheticMFAEvent.objects.create(factor=item, outcome=_ENROLLMENT)
    return item.pk


def verify(*, dealership, user, factor, code):
    """Consume matching synthetic time steps; return False on rejection or throttling.

    PostgreSQL serializes checks on the factor row. SQLite is for single-worker
    development only: lock failures propagate rather than accepting a token.
    """
    mfa_secrets._config()  # Gate and key configuration must hold on every call.
    mfa_secrets._context(dealership, user, factor)
    context = {'dealership': dealership, 'user': user, 'factor': factor}
    with transaction.atomic():
        item = SyntheticMFAFactor.objects.select_for_update().filter(
            dealership_ref=dealership, user_ref=user, factor_ref=factor,
        ).first()
        if item is None:
            return False
        # Earlier enrollments lack collision-aware consumption history and cannot
        # be safely upgraded in place. Create a new synthetic factor instead.
        if not SyntheticMFAEvent.objects.filter(factor=item, outcome=_ENROLLMENT).exists():
            return False
        now = timezone.now()
        if item.locked_until and now < item.locked_until:
            return False
        if item.locked_until:
            item.failure_count = 0
            item.locked_until = None
        secret = mfa_secrets.decrypt_synthetic_secret(item.secret_envelope, **context)
        if len(secret) != len(_PREFIX) + _SEED_BYTES:
            raise mfa_secrets.SyntheticSecretError('Synthetic MFA seed is invalid.')
        totp = TOTP(secret[len(_PREFIX):], step=30, digits=6)
        totp.time = now.timestamp()
        valid = isinstance(code, str) and bool(_CODE.fullmatch(code)) and totp.verify(
            int(code), tolerance=1, min_t=item.last_step + 1,
        )
        if valid:
            last_match = _last_continuous_match(totp, code)
            valid = last_match is not None
        if valid:
            item.last_step = last_match
            item.failure_count = 0
            outcome = 'accepted'
        else:
            item.failure_count += 1
            if item.failure_count >= _FAILURES:
                item.locked_until = now + timedelta(seconds=_LOCK_SECONDS)
            outcome = 'rejected'
        item.save(update_fields=['last_step', 'failure_count', 'locked_until'])
        SyntheticMFAEvent.objects.create(factor=item, outcome=outcome)
        return bool(valid)

# SPDX-License-Identifier: MPL-2.0
import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as dt_timezone
from threading import Barrier
from unittest.mock import patch

from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django_otp.oath import TOTP

from .mfa_prototype import enroll, verify
from .mfa_secrets import SyntheticSecretError, decrypt_synthetic_secret, encrypt_synthetic_secret
from .models import SyntheticMFAEvent, SyntheticMFAFactor


class SyntheticMFASetup:
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'RAILET_DEV_MFA_SYNTHETIC': '1',
            'RAILET_DEV_MFA_ACTIVE_KEY': 'test-key',
            'RAILET_DEV_MFA_KEYS': json.dumps({'test-key': base64.urlsafe_b64encode(b'k' * 32).decode()}),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.ctx = {'dealership': 'synthetic-dealer', 'user': 'synthetic-person', 'factor': 'synthetic-factor'}
        self.pk = enroll(**self.ctx)
        self.now = datetime(2026, 11, 7, 12, 0, tzinfo=dt_timezone.utc)

    def code(self, at):
        item = SyntheticMFAFactor.objects.get(pk=self.pk)
        secret = decrypt_synthetic_secret(item.secret_envelope, **self.ctx)
        totp = TOTP(secret[len(b'synthetic:'):])
        totp.time = at.timestamp()
        return f'{totp.token():06d}'

    def attempt(self, code, at=None, ctx=None):
        with patch('core.mfa_prototype.timezone.now', return_value=at or self.now):
            return verify(**(ctx or self.ctx), code=code)

    def collision_fixture(self):
        # Independently precomputed using django-otp: these nonadjacent steps
        # produce the same six digits for this invented, fixed seed.
        seed = b'RailetSyntheticSeed!'
        first, second = 59706093, 59706095
        envelope = encrypt_synthetic_secret(b'synthetic:' + seed, **self.ctx)
        SyntheticMFAFactor.objects.filter(pk=self.pk).update(secret_envelope=envelope)
        at = datetime.fromtimestamp(first * 30, tz=dt_timezone.utc)
        self.assertEqual(self.code(at), '587707')
        self.assertEqual(self.code(datetime.fromtimestamp(second * 30, tz=dt_timezone.utc)), '587707')
        return at, second


@override_settings(DEBUG=True)
class SyntheticMFAPrototypeTests(SyntheticMFASetup, TestCase):
    def test_colliding_code_cannot_be_reused_when_later_step_enters_window(self):
        at, second = self.collision_fixture()
        self.assertTrue(self.attempt('587707', at))
        self.assertEqual(SyntheticMFAFactor.objects.get(pk=self.pk).last_step, second)
        self.assertFalse(self.attempt('587707', at + timedelta(seconds=30)))
        self.assertFalse(self.attempt('587707', at + timedelta(seconds=60)))
        event_values = list(SyntheticMFAEvent.objects.values_list('outcome', flat=True))
        self.assertEqual(event_values, ['enrolled-v2', 'accepted', 'rejected', 'rejected'])

    def test_collision_scan_cap_fails_closed_and_throttles(self):
        with patch('core.mfa_prototype.TOTP.token', return_value=123456):
            for _ in range(5):
                self.assertFalse(self.attempt('123456'))
        factor = SyntheticMFAFactor.objects.get(pk=self.pk)
        self.assertEqual(factor.last_step, -1)
        self.assertEqual(factor.failure_count, 5)
        self.assertIsNotNone(factor.locked_until)
        self.assertEqual(list(SyntheticMFAEvent.objects.values_list('outcome', flat=True)), ['enrolled-v2'] + ['rejected'] * 5)

    def test_chained_collision_windows_consume_all_matching_steps(self):
        start = 59706093
        at = datetime.fromtimestamp(start * 30, tz=dt_timezone.utc)
        matches = {start, start + 3, start + 6}
        def simulated_token(totp):
            return 444444 if totp.t() in matches else 123456
        with patch('core.mfa_prototype.TOTP.token', autospec=True, side_effect=simulated_token):
            self.assertTrue(self.attempt('444444', at))
            self.assertFalse(self.attempt('444444', at + timedelta(seconds=120)))
            self.assertEqual(SyntheticMFAFactor.objects.get(pk=self.pk).last_step, start + 6)

    def test_legacy_factor_fails_closed(self):
        old_ctx = dict(self.ctx, factor='synthetic-legacy')
        item = SyntheticMFAFactor.objects.create(
            dealership_ref=old_ctx['dealership'], user_ref=old_ctx['user'], factor_ref=old_ctx['factor'],
            secret_envelope=encrypt_synthetic_secret(b'synthetic:RailetSyntheticSeed!', **old_ctx),
            last_step=59706093,
        )
        SyntheticMFAEvent.objects.create(factor=item, outcome='enrolled')
        at = datetime.fromtimestamp(59706094 * 30, tz=dt_timezone.utc)
        self.assertFalse(self.attempt('587707', at=at, ctx=old_ctx))
        item.refresh_from_db()
        self.assertEqual(item.last_step, 59706093)
        self.assertEqual(SyntheticMFAEvent.objects.filter(factor=item).count(), 1)

    def test_valid_skew_expiration_and_replay(self):
        self.assertFalse(self.attempt(self.code(self.now - timedelta(seconds=60))))
        self.assertTrue(self.attempt(self.code(self.now - timedelta(seconds=30))))
        self.assertFalse(self.attempt(self.code(self.now - timedelta(seconds=30))))
        self.assertTrue(self.attempt(self.code(self.now + timedelta(seconds=30))))
        self.assertFalse(self.attempt(self.code(self.now)))
        self.assertEqual(list(SyntheticMFAEvent.objects.values_list('outcome', flat=True)),
                         ['enrolled-v2', 'rejected', 'accepted', 'rejected', 'accepted', 'rejected'])

    def test_throttle_is_per_factor_and_resets_after_timeout(self):
        other = dict(self.ctx, factor='synthetic-other')
        enroll(**other)
        for _ in range(5):
            self.assertFalse(self.attempt('invalid'))
        item = SyntheticMFAFactor.objects.get(pk=self.pk)
        self.assertEqual(item.failure_count, 5)
        self.assertFalse(self.attempt(self.code(self.now)))
        self.assertEqual(SyntheticMFAEvent.objects.filter(factor_id=self.pk).count(), 6)
        self.assertFalse(self.attempt('bad', ctx=other))
        self.assertEqual(SyntheticMFAFactor.objects.get(factor_ref='synthetic-other').failure_count, 1)
        later = self.now + timedelta(seconds=60)
        self.assertTrue(self.attempt(self.code(later), at=later))
        item.refresh_from_db()
        self.assertEqual(item.failure_count, 0)
        self.assertIsNone(item.locked_until)

    def test_context_tampering_and_gate_fail_closed(self):
        self.assertFalse(self.attempt(self.code(self.now), ctx=dict(self.ctx, dealership='synthetic-elsewhere')))
        item = SyntheticMFAFactor.objects.get(pk=self.pk)
        envelope = dict(item.secret_envelope)
        envelope['ciphertext'] = envelope['ciphertext'][:-2] + ('AA' if envelope['ciphertext'][-2:] != 'AA' else 'BB')
        SyntheticMFAFactor.objects.filter(pk=self.pk).update(secret_envelope=envelope)
        with self.assertRaises(SyntheticSecretError):
            self.attempt('123456')
        self.assertEqual(SyntheticMFAEvent.objects.count(), 1)
        with patch.dict(os.environ, {'RAILET_DEV_MFA_SYNTHETIC': '0'}), self.assertRaises(SyntheticSecretError):
            self.attempt('123456')
        with override_settings(DEBUG=False), self.assertRaises(SyntheticSecretError):
            enroll(**dict(self.ctx, factor='synthetic-new'))
        with patch.dict(os.environ, {'RAILET_DEV_MFA_KEYS': ''}), self.assertRaises(SyntheticSecretError):
            self.attempt('123456')
        with self.assertRaises(SyntheticSecretError):
            enroll(**dict(self.ctx, user='real-user'))

    def test_audit_immutable_and_write_failure_rolls_back_consumption(self):
        event = SyntheticMFAEvent.objects.get(factor_id=self.pk)
        for operation in ('update', 'delete'):
            with self.subTest(operation=operation), self.assertRaises(DatabaseError), transaction.atomic():
                query = SyntheticMFAEvent.objects.filter(pk=event.pk)
                query.update(outcome='changed') if operation == 'update' else query.delete()
        token = self.code(self.now)
        with patch('core.mfa_prototype.SyntheticMFAEvent.objects.create', side_effect=DatabaseError('audit failure')):
            with self.assertRaises(DatabaseError):
                self.attempt(token)
        self.assertEqual(SyntheticMFAFactor.objects.get(pk=self.pk).last_step, -1)
        self.assertTrue(self.attempt(token))


@override_settings(DEBUG=True)
class SyntheticMFAConcurrencyTests(SyntheticMFASetup, TransactionTestCase):
    def setUp(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL row-lock test; SQLite does not support select_for_update')
        super().setUp()

    def test_postgresql_concurrent_one_use(self):
        token = self.code(self.now)
        barrier = Barrier(2)
        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return self.attempt(token)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(SyntheticMFAEvent.objects.filter(outcome='accepted').count(), 1)

    def test_postgresql_concurrent_collision_one_use(self):
        at, second = self.collision_fixture()
        barrier = Barrier(2)
        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return verify(**self.ctx, code='587707')
            finally:
                close_old_connections()
        # Both matching timesteps are already inside the accepted window.
        with patch('core.mfa_prototype.timezone.now', return_value=at + timedelta(seconds=30)):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(SyntheticMFAFactor.objects.get(pk=self.pk).last_step, second)
        self.assertEqual(SyntheticMFAEvent.objects.filter(outcome='accepted').count(), 1)

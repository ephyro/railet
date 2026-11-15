# SPDX-License-Identifier: MPL-2.0
import base64
import json
import os
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from .mfa_secrets import (SyntheticSecretError, encrypt_synthetic_secret,
                          decrypt_synthetic_secret, rotate_synthetic_secret)


def b64(value):
    return base64.urlsafe_b64encode(value).decode('ascii')


@override_settings(DEBUG=True)
class SyntheticMFASecretsTests(SimpleTestCase):
    def setUp(self):
        self.key_a = b64(bytes(range(32)))
        self.key_b = b64(bytes(range(32, 64)))
        self.env = {'RAILET_DEV_MFA_SYNTHETIC': '1',
                    'RAILET_DEV_MFA_KEYS': json.dumps({'test-a': self.key_a, 'test-b': self.key_b}),
                    'RAILET_DEV_MFA_ACTIVE_KEY': 'test-a'}
        self.context = {'dealership': 'synthetic-dealer-1', 'user': 'synthetic-user-1', 'factor': 'synthetic-factor-1'}
        self.secret = b'synthetic:invented demo factor; never a real OTP seed'
        self.environment = patch.dict(os.environ, self.env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def encrypt(self):
        return encrypt_synthetic_secret(self.secret, **self.context)

    def test_round_trip_random_nonce_and_no_plaintext(self):
        first, second = self.encrypt(), self.encrypt()
        self.assertNotEqual(first['nonce'], second['nonce'])
        self.assertNotEqual(first['ciphertext'], second['ciphertext'])
        self.assertEqual(decrypt_synthetic_secret(first, **self.context), self.secret)
        self.assertNotIn(self.secret.decode(), json.dumps(first))
        self.assertNotIn(self.key_a, json.dumps(first))

    def test_operations_do_not_log_secrets_or_key_material(self):
        with patch('logging.Logger._log') as emit:
            item = self.encrypt()
            self.assertEqual(decrypt_synthetic_secret(item, **self.context), self.secret)
            with self.assertRaises(SyntheticSecretError) as error:
                decrypt_synthetic_secret(item, **(self.context | {'user': 'synthetic-other'}))
        emit.assert_not_called()
        self.assertNotIn(self.secret.decode(), str(error.exception))
        self.assertNotIn(self.key_a, str(error.exception))

    def test_every_context_field_is_authenticated(self):
        item = self.encrypt()
        for field in self.context:
            with self.subTest(field=field):
                changed = self.context | {field: 'synthetic-different'}
                with self.assertRaises(SyntheticSecretError): decrypt_synthetic_secret(item, **changed)
        for value in ('1', 'actual-user', '', '../synthetic-user', 'synthetic-\n'):
            with self.subTest(value=value), self.assertRaises(SyntheticSecretError):
                decrypt_synthetic_secret(item, **(self.context | {'user': value}))

    def test_tampering_all_envelope_fields_and_malformed_inputs(self):
        item = self.encrypt()
        modified = base64.urlsafe_b64decode(item['ciphertext'])
        broken = bytes([modified[0] ^ 1]) + modified[1:]
        cases = [item | {'ciphertext': b64(broken)}, item | {'nonce': b64(b'x' * 12)},
                 item | {'key_id': 'test-b'}, item | {'format': 'other'},
                 item | {'ciphertext': '!!!'}, item | {'nonce': ''}, item | {'extra': 'x'},
                 {key:value for key,value in item.items() if key != 'nonce'}, None, {},
                 item | {'ciphertext': 'a'*10000}]
        for case in cases:
            with self.subTest(case_type=type(case).__name__), self.assertRaises(SyntheticSecretError):
                decrypt_synthetic_secret(case, **self.context)

    def test_rotation_and_missing_old_key_fail_closed(self):
        old = self.encrypt()
        os.environ['RAILET_DEV_MFA_ACTIVE_KEY'] = 'test-b'
        rotated = rotate_synthetic_secret(old, **self.context)
        self.assertEqual(rotated['key_id'], 'test-b')
        self.assertNotEqual(rotated['nonce'], old['nonce'])
        self.assertEqual(decrypt_synthetic_secret(rotated, **self.context), self.secret)
        self.assertEqual(decrypt_synthetic_secret(old, **self.context), self.secret)
        os.environ['RAILET_DEV_MFA_KEYS'] = json.dumps({'test-b': self.key_b})
        with self.assertRaises(SyntheticSecretError): decrypt_synthetic_secret(old, **self.context)
        self.assertEqual(decrypt_synthetic_secret(rotated, **self.context), self.secret)

    def test_missing_bad_duplicate_keys_and_active_id_fail_closed(self):
        cases = [('', 'test-a'), ('{}', 'test-a'), ('not-json', 'test-a'),
                 (json.dumps({'test-a':'short'}), 'test-a'),
                 (json.dumps({'test-a':self.key_a}), 'missing'),
                 ('{"test-a":"' + self.key_a + '","test-a":"' + self.key_b + '"}', 'test-a'),
                 (json.dumps({'test-a':self.key_a, 'test-b':self.key_a}), 'test-a')]
        for keys, active in cases:
            with self.subTest(case=len(keys)):
                os.environ['RAILET_DEV_MFA_KEYS'] = keys
                os.environ['RAILET_DEV_MFA_ACTIVE_KEY'] = active
                with self.assertRaises(SyntheticSecretError) as error: self.encrypt()
                self.assertNotIn(self.key_a, str(error.exception))
                if keys:
                    self.assertNotIn(keys, str(error.exception))

    def test_gate_and_only_synthetic_bytes(self):
        item = self.encrypt()
        for secret in (b'real-seed', b'synthetic:', 'synthetic:text', b'synthetic:' + b'x'*4096):
            with self.subTest(secret_type=type(secret).__name__), self.assertRaises(SyntheticSecretError):
                encrypt_synthetic_secret(secret, **self.context)
        with override_settings(DEBUG=False):
            for operation in (self.encrypt, lambda: decrypt_synthetic_secret(item, **self.context),
                              lambda: rotate_synthetic_secret(item, **self.context)):
                with self.assertRaises(SyntheticSecretError): operation()
        del os.environ['RAILET_DEV_MFA_SYNTHETIC']
        for operation in (self.encrypt, lambda: decrypt_synthetic_secret(item, **self.context),
                          lambda: rotate_synthetic_secret(item, **self.context)):
            with self.assertRaises(SyntheticSecretError): operation()

# SPDX-License-Identifier: MPL-2.0
"""Offline synthetic MFA secret encryption experiment; never use for real factors.

No database, authentication integration, persistence, logging or key generation is
provided. Callers own safe storage and atomic rotation of synthetic records.
"""
import base64
import binascii
import json
import os
import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

FORMAT = 'railet-synthetic-mfa-secret-v1'
MAX_SECRET_BYTES = 4096
_IDENTIFIER = re.compile(r'synthetic-[A-Za-z0-9_-]{1,80}\Z')
_KEY_ID = re.compile(r'[A-Za-z0-9_-]{1,48}\Z')
_FIELDS = frozenset(('format', 'key_id', 'nonce', 'ciphertext'))


class SyntheticSecretError(Exception):
    """Operation denied or data invalid; messages never include input values."""


def _config():
    if not settings.DEBUG or os.environ.get('RAILET_DEV_MFA_SYNTHETIC') != '1':
        raise SyntheticSecretError('Synthetic MFA encryption is disabled.')
    raw = os.environ.get('RAILET_DEV_MFA_KEYS')
    active = os.environ.get('RAILET_DEV_MFA_ACTIVE_KEY')
    if not raw or len(raw) > 4096 or not isinstance(active, str) or not _KEY_ID.fullmatch(active):
        raise SyntheticSecretError('Synthetic MFA key configuration is invalid.')
    def unique_pairs(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError
            result[name] = value
        return result
    try:
        encoded = json.loads(raw, object_pairs_hook=unique_pairs)
        if not isinstance(encoded, dict) or not 1 <= len(encoded) <= 16:
            raise ValueError
        keys = {}
        for name, value in encoded.items():
            if not isinstance(name, str) or not _KEY_ID.fullmatch(name) or not isinstance(value, str):
                raise ValueError
            key = base64.b64decode(value, altchars=b'-_', validate=True)
            if len(key) != 32 or base64.urlsafe_b64encode(key).decode('ascii') != value:
                raise ValueError
            keys[name] = key
        if active not in keys or len(set(keys.values())) != len(keys):
            raise ValueError
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        raise SyntheticSecretError('Synthetic MFA key configuration is invalid.') from None
    return active, keys


def _context(dealership, user, factor):
    values = (dealership, user, factor)
    if not all(isinstance(value, str) and _IDENTIFIER.fullmatch(value) for value in values):
        raise SyntheticSecretError('Synthetic MFA context is invalid.')
    return values


def _aad(key_id, context):
    return json.dumps([FORMAT, key_id, *context], ensure_ascii=True, separators=(',', ':')).encode('ascii')


def _encode(data):
    return base64.urlsafe_b64encode(data).decode('ascii')


def _decode(value, limit):
    if not isinstance(value, str) or len(value) > limit:
        raise SyntheticSecretError('Synthetic MFA envelope is invalid.')
    try:
        decoded = base64.b64decode(value, altchars=b'-_', validate=True)
        if _encode(decoded) != value:
            raise ValueError
        return decoded
    except (ValueError, UnicodeError, binascii.Error):
        raise SyntheticSecretError('Synthetic MFA envelope is invalid.') from None


def encrypt_synthetic_secret(secret, *, dealership, user, factor):
    """Encrypt invented bytes only; synthetic identifiers are separate from app IDs."""
    active, keys = _config()
    context = _context(dealership, user, factor)
    if not isinstance(secret, bytes) or not secret.startswith(b'synthetic:') or not 11 <= len(secret) <= MAX_SECRET_BYTES:
        raise SyntheticSecretError('Only explicitly marked synthetic bytes are allowed.')
    nonce = os.urandom(12)
    ciphertext = AESGCM(keys[active]).encrypt(nonce, secret, _aad(active, context))
    return {'format': FORMAT, 'key_id': active, 'nonce': _encode(nonce), 'ciphertext': _encode(ciphertext)}


def decrypt_synthetic_secret(envelope, *, dealership, user, factor):
    """Authenticate context and envelope before returning invented bytes."""
    _, keys = _config()
    context = _context(dealership, user, factor)
    if not isinstance(envelope, dict) or set(envelope) != _FIELDS or envelope.get('format') != FORMAT:
        raise SyntheticSecretError('Synthetic MFA envelope is invalid.')
    key_id = envelope.get('key_id')
    if not isinstance(key_id, str) or key_id not in keys:
        raise SyntheticSecretError('Synthetic MFA key is unavailable.')
    nonce = _decode(envelope['nonce'], 16)
    ciphertext = _decode(envelope['ciphertext'], 5500)
    if len(nonce) != 12 or not 27 <= len(ciphertext) <= MAX_SECRET_BYTES + 16:
        raise SyntheticSecretError('Synthetic MFA envelope is invalid.')
    try:
        secret = AESGCM(keys[key_id]).decrypt(nonce, ciphertext, _aad(key_id, context))
    except (InvalidTag, ValueError):
        raise SyntheticSecretError('Synthetic MFA envelope authentication failed.') from None
    if not secret.startswith(b'synthetic:'):
        raise SyntheticSecretError('Synthetic MFA envelope authentication failed.')
    return secret


def rotate_synthetic_secret(envelope, *, dealership, user, factor):
    """Re-encrypt with the configured active key and a fresh random nonce."""
    context = {'dealership': dealership, 'user': user, 'factor': factor}
    secret = decrypt_synthetic_secret(envelope, **context)
    return encrypt_synthetic_secret(secret, **context)

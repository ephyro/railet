# SPDX-License-Identifier: MPL-2.0
"""Offline DocuSeal request and local mock-transport rehearsal.

Never sends live network requests, emails, SMS, or legally binding signatures.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import hmac
import io
import json
from urllib.parse import urlparse
from uuid import UUID
from django.core.exceptions import ValidationError

LOOPBACK_HOSTS = ('127.0.0.1', 'localhost', '::1')
ALLOWED_WEBHOOK_EVENTS = ('form.viewed', 'form.started', 'form.completed', 'submission.completed')


@dataclass(frozen=True)
class TestSigner:
    name: str
    email: str
    role: str


@dataclass(frozen=True)
class SandboxConfig:
    base_url: str
    expected_version: str


def validate_loopback_sandbox(config):
    """Require an explicit loopback-only URL and expected version before any local test call."""
    if not isinstance(config, SandboxConfig):
        raise ValidationError('Provide a SandboxConfig instance.')
    version = config.expected_version.strip()
    if not version or len(version) > 40:
        raise ValidationError('Specify the expected DocuSeal version to verify before connecting.')
    parsed = urlparse(config.base_url)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
        raise ValidationError('Use an http/https loopback URL without embedded credentials.')
    if parsed.hostname not in LOOPBACK_HOSTS:
        raise ValidationError('Test DocuSeal connections are restricted to loopback (127.0.0.1, localhost, or ::1).')
    return config


def prepare_test_submission(*, template_id, signer, request_key):
    """Construct a no-notification template request for an invented signer.

    This function deliberately has no HTTP transport, credentials, or callback.
    External ID is a correlation key, not a claim of provider-side idempotency.
    """
    if isinstance(template_id, bool) or not isinstance(template_id, int) or template_id <= 0:
        raise ValidationError('Use a positive test template ID.')
    if not isinstance(signer, TestSigner):
        raise ValidationError('Use an invented test signer.')
    if not isinstance(signer.name, str) or not isinstance(signer.role, str) or not isinstance(signer.email, str):
        raise ValidationError('Use text for the test signer name, role and email.')
    if not signer.name.strip() or len(signer.name) > 120 or not signer.role.strip() or len(signer.role) > 120:
        raise ValidationError('Enter a test signer name and template role.')
    from django.core.validators import validate_email
    validate_email(signer.email)
    if not signer.email.lower().endswith('@example.invalid'):
        raise ValidationError('Use an invented @example.invalid email address.')
    try:
        key = UUID(str(request_key))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError('Use a valid test request key.') from error
    return {
        'template_id': template_id,
        'send_email': False,
        'send_sms': False,
        'submitters': [{'name': signer.name.strip(), 'email': signer.email.lower(),
                        'role': signer.role.strip(), 'external_id': str(key),
                        'send_email': False, 'send_sms': False}],
    }


def verify_submission_payload(payload):
    """Only accept the exact, single-signer shape produced by the offline builder."""
    if not isinstance(payload, dict):
        raise ValidationError('Submission payload must be a dictionary.')
    if set(payload) != {'template_id', 'send_email', 'send_sms', 'submitters'}:
        raise ValidationError('Unexpected or missing test submission fields.')
    submitters = payload.get('submitters')
    if not isinstance(submitters, list) or len(submitters) != 1 or not isinstance(submitters[0], dict):
        raise ValidationError('Include exactly one invented test submitter.')
    sub = submitters[0]
    if set(sub) != {'name', 'email', 'role', 'external_id', 'send_email', 'send_sms'}:
        raise ValidationError('Unexpected or missing test submitter fields.')
    if any(value is not False for value in (payload['send_email'], payload['send_sms'], sub['send_email'], sub['send_sms'])):
        raise ValidationError('Email and SMS must both be disabled at each level.')
    expected = prepare_test_submission(template_id=payload['template_id'],
        signer=TestSigner(sub['name'], sub['email'], sub['role']), request_key=sub['external_id'])
    if expected != payload:
        raise ValidationError('Test submission must use canonical invented values.')
    return payload


def make_synthetic_pdf_fixture():
    """Create a single invented, visibly marked PDF, with no signer or contract."""
    from PIL import Image, ImageDraw
    image = Image.new('RGB', (612, 792), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((45, 70), 'SYNTHETIC TEST ONLY - NOT A CONTRACT', fill='black')
    draw.text((45, 110), 'Practice document for an isolated signing rehearsal.', fill='black')
    output = io.BytesIO()
    image.save(output, format='PDF', resolution=72.0, title='Synthetic test only')
    return output.getvalue()


def verify_webhook_event(*, headers, raw_body, expected_secret, seen_event_keys=None):
    """Verify a local mock webhook event using an invented shared-secret header and schema.

    SECURITY LIMITATION: The `X-DocuSeal-Webhook-Secret` header, payload schema,
    and optional in-memory `seen_event_keys` set are unverified local mock
    assumptions for unit testing only. They do NOT establish actual DocuSeal
    webhook authentication, nor do they provide durable, transactional replay
    protection across restarts or workers. Does not mark any deal or document
    legally signed.
    """
    if not expected_secret or not isinstance(expected_secret, str) or len(expected_secret) < 16:
        raise ValidationError('Configure a webhook secret of at least 16 characters.')
    if not isinstance(headers, dict):
        raise ValidationError('Webhook headers must be a dictionary.')
    provided = next((v for k, v in headers.items() if k.lower() == 'x-docuseal-webhook-secret'), '')
    if not isinstance(provided, str) or not hmac.compare_digest(provided, expected_secret):
        raise ValidationError('Invalid webhook authentication secret.')
    try:
        body = json.loads(raw_body.decode('utf-8') if isinstance(raw_body, bytes) else raw_body)
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError('Invalid webhook JSON payload.') from error
    if not isinstance(body, dict):
        raise ValidationError('Webhook payload must be a JSON object.')
    event_type = body.get('event_type')
    if event_type not in ALLOWED_WEBHOOK_EVENTS:
        raise ValidationError('Unsupported webhook event type.')
    data = body.get('data')
    if not isinstance(data, dict):
        raise ValidationError('Webhook data object is required.')
    email = str(data.get('email', '')).lower()
    if not email.endswith('@example.invalid'):
        raise ValidationError('Webhook signer must use an @example.invalid address.')
    try:
        external_id = str(UUID(str(data.get('external_id', ''))))
    except (ValueError, TypeError):
        raise ValidationError('Webhook data must carry a valid UUID external_id.')
    submission_id = data.get('submission_id')
    if isinstance(submission_id, bool) or not isinstance(submission_id, int) or submission_id <= 0:
        raise ValidationError('Webhook data must carry a positive integer submission_id.')
    event_key = f'{submission_id}:{external_id}:{event_type}'
    if seen_event_keys is not None and event_key in seen_event_keys:
        return {'mock_only': True, 'duplicate': True, 'event_key': event_key, 'event_type': event_type, 'external_id': external_id, 'submission_id': submission_id}
    if seen_event_keys is not None:
        seen_event_keys.add(event_key)
    return {'mock_only': True, 'duplicate': False, 'event_key': event_key, 'event_type': event_type, 'external_id': external_id, 'submission_id': submission_id}


def verify_test_pdf_artifact(pdf_bytes, *, expected_sha256):
    """Verify a retrieved synthetic PDF starts with %PDF-, is bounded, and matches its SHA-256."""
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b'%PDF-') or len(pdf_bytes) > 5 * 1024 * 1024:
        raise ValidationError('Artifact must be a bounded PDF byte stream.')
    actual = hashlib.sha256(pdf_bytes).hexdigest()
    if not isinstance(expected_sha256, str) or not hmac.compare_digest(actual, expected_sha256.lower()):
        raise ValidationError('Retrieved PDF SHA-256 did not match expected digest.')
    return actual


class LocalMockDocuSealTransport:
    """In-memory mock transport for isolated contract testing without a running server or network.

    SECURITY LIMITATION: Deduplication on `external_id` and environment checks here
    are in-memory mock behaviors only; they do not prove that a real DocuSeal
    server enforces `external_id` idempotency on `POST /submissions`.
    """

    def __init__(self, *, config, version='2.0.0-mock', egress_disabled=True):
        self.config = validate_loopback_sandbox(config)
        self.version = version
        self.egress_disabled = egress_disabled
        self._submissions_by_id = {}
        self._id_by_external = {}
        self._next_id = 1000

    def verify_environment(self):
        if not self.egress_disabled:
            raise ValidationError('Outbound email/SMS egress must be disabled in the test environment.')
        if self.version != self.config.expected_version:
            raise ValidationError('Mock provider version does not match expected SandboxConfig version.')
        return {'mock_only': True, 'version': self.version, 'egress_disabled': True, 'loopback_only': True}

    def submit(self, payload):
        self.verify_environment()
        verify_submission_payload(payload)
        ext_id = payload['submitters'][0]['external_id']
        if ext_id in self._id_by_external:
            existing = self._submissions_by_id[self._id_by_external[ext_id]]
            if existing['request'] != payload:
                raise ValidationError('External ID was already used for a different test submission payload.')
            return deepcopy(existing['response'])
        submission_id = self._next_id
        self._next_id += 1
        synthetic_pdf = make_synthetic_pdf_fixture()
        response = {
            'mock_only': True,
            'submission_id': submission_id,
            'status': 'pending',
            'external_id': ext_id,
            'artifact_bytes': synthetic_pdf,
            'artifact_sha256': hashlib.sha256(synthetic_pdf).hexdigest(),
        }
        self._id_by_external[ext_id] = submission_id
        self._submissions_by_id[submission_id] = {'request': deepcopy(payload), 'response': response}
        return deepcopy(response)

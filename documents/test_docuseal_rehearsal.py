# SPDX-License-Identifier: MPL-2.0
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import skipUnless
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from .signing.docuseal import (
    LocalMockDocuSealTransport,
    SandboxConfig,
    TestSigner,
    prepare_test_submission,
    make_synthetic_pdf_fixture,
    validate_loopback_sandbox,
    verify_submission_payload,
    verify_test_pdf_artifact,
    verify_webhook_event,
)


class DocusealRehearsalTests(SimpleTestCase):
    def test_test_signer_has_no_notifications_or_auto_signature(self):
        key=uuid4()
        payload=prepare_test_submission(template_id=42,signer=TestSigner('Practice Buyer','test@example.invalid','Buyer'),request_key=key)
        self.assertFalse(payload['send_email']);self.assertFalse(payload['send_sms'])
        self.assertFalse(payload['submitters'][0]['send_email']);self.assertFalse(payload['submitters'][0]['send_sms'])
        self.assertNotIn('completed',payload['submitters'][0])
        self.assertEqual(payload['submitters'][0]['external_id'],str(key))

    def test_rejects_real_addresses_and_invalid_templates(self):
        for email in ('person@example.com','bad@example.invalid.evil','not-an-email'):
            with self.assertRaises(ValidationError):
                prepare_test_submission(template_id=42,signer=TestSigner('Practice',email,'Buyer'),request_key=uuid4())
        for template_id in (0,-1,True,'42'):
            with self.assertRaises(ValidationError):
                prepare_test_submission(template_id=template_id,signer=TestSigner('Practice','test@example.invalid','Buyer'),request_key=uuid4())

    def test_loopback_sandbox_version_and_egress_gates(self):
        for bad_url in ('https://api.docuseal.com', 'http://192.168.1.10:3000', 'http://user:pass@127.0.0.1:3000', 'ftp://127.0.0.1:3000'):
            with self.assertRaises(ValidationError):
                validate_loopback_sandbox(SandboxConfig(base_url=bad_url, expected_version='2.0.0-mock'))
        with self.assertRaises(ValidationError):
            validate_loopback_sandbox(SandboxConfig(base_url='http://127.0.0.1:3000', expected_version=''))

        config = SandboxConfig(base_url='http://127.0.0.1:3000', expected_version='2.0.0-mock')
        with self.assertRaises(ValidationError):
            LocalMockDocuSealTransport(config=config, version='2.0.0-mock', egress_disabled=False).verify_environment()
        with self.assertRaises(ValidationError):
            LocalMockDocuSealTransport(config=config, version='9.9.9', egress_disabled=True).verify_environment()

    def test_mock_transport_idempotency_payload_guards_and_artifact_hash(self):
        config = SandboxConfig(base_url='http://127.0.0.1:3000', expected_version='2.0.0-mock')
        transport = LocalMockDocuSealTransport(config=config)
        key = uuid4()
        payload = prepare_test_submission(template_id=7, signer=TestSigner('Practice Buyer', 'buyer@example.invalid', 'Buyer'), request_key=key)
        first = transport.submit(payload)
        second = transport.submit(payload)
        self.assertTrue(first['mock_only'])
        self.assertTrue(transport.verify_environment()['mock_only'])
        self.assertFalse( hasattr(config, 'webhook_secret_header') )
        self.assertEqual(first['submission_id'], second['submission_id'])
        self.assertEqual(verify_test_pdf_artifact(first['artifact_bytes'], expected_sha256=first['artifact_sha256']), first['artifact_sha256'])

        # Conflicting retry with same key is rejected
        different = prepare_test_submission(template_id=8, signer=TestSigner('Practice Buyer', 'buyer@example.invalid', 'Buyer'), request_key=key)
        with self.assertRaises(ValidationError):
            transport.submit(different)

        # Tampered artifact bytes or digest rejected
        with self.assertRaises(ValidationError):
            verify_test_pdf_artifact(first['artifact_bytes'] + b'tamper', expected_sha256=first['artifact_sha256'])
        with self.assertRaises(ValidationError):
            verify_test_pdf_artifact(b'not-a-pdf', expected_sha256=first['artifact_sha256'])

        # Submission payload verifier blocks notification flags or auto-completion
        for bad_mutation in (
            lambda p: p.update({'send_email': True}),
            lambda p: p['submitters'][0].update({'send_sms': True}),
            lambda p: p['submitters'][0].update({'completed': True}),
            lambda p: p.update({'completed': True}),
            lambda p: p.update({'bcc_completed': 'real@example.com'}),
            lambda p: p['submitters'][0].update({'phone': '+15551234567'}),
            lambda p: p['submitters'][0].update({'require_email_2fa': True}),
            lambda p: p['submitters'].append(dict(p['submitters'][0])),
            lambda p: p['submitters'][0].update({'email': 'invalid@@example.invalid'}),
            lambda p: p.update({'template_id': True}),
        ):
            mutated = prepare_test_submission(template_id=7, signer=TestSigner('Practice Buyer', 'buyer@example.invalid', 'Buyer'), request_key=uuid4())
            bad_mutation(mutated)
            with self.assertRaises(ValidationError):
                verify_submission_payload(mutated)

    @skipUnless(shutil.which('pdfinfo'), 'pdfinfo is needed for independent PDF parsing')
    def test_synthetic_fixture_is_a_parseable_single_page_pdf(self):
        artifact = make_synthetic_pdf_fixture()
        with tempfile.TemporaryDirectory(prefix='railet-docuseal-pdf-') as directory:
            path = Path(directory) / 'synthetic.pdf'
            path.write_bytes(artifact)
            result = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True, timeout=10, check=True)
        self.assertIn('Pages:', result.stdout)
        self.assertRegex(result.stdout, r'Pages:\s+1\b')
        self.assertLess(len(artifact), 5 * 1024 * 1024)

    def test_webhook_authentication_synthetic_signer_and_replay_detection(self):
        secret = 'synthetic-webhook-secret-key-2026'
        ext_id = str(uuid4())
        seen = set()
        raw = json.dumps({
            'event_type': 'form.completed',
            'data': {'submission_id': 1000, 'external_id': ext_id, 'email': 'buyer@example.invalid'},
        }).encode('utf-8')

        first = verify_webhook_event(headers={'X-DocuSeal-Webhook-Secret': secret}, raw_body=raw, expected_secret=secret, seen_event_keys=seen)
        self.assertTrue(first['mock_only'])
        self.assertFalse(first['duplicate'])
        replay = verify_webhook_event(headers={'x-docuseal-webhook-secret': secret}, raw_body=raw, expected_secret=secret, seen_event_keys=seen)
        self.assertTrue(replay['mock_only'])
        self.assertTrue(replay['duplicate'])

        # Wrong secret, short secret, non-synthetic email, or unknown event rejected
        with self.assertRaises(ValidationError):
            verify_webhook_event(headers={'X-DocuSeal-Webhook-Secret': 'wrong'}, raw_body=raw, expected_secret=secret)
        with self.assertRaises(ValidationError):
            verify_webhook_event(headers={'X-DocuSeal-Webhook-Secret': 'short'}, raw_body=raw, expected_secret='short')
        for bad_payload in (
            {'event_type': 'unknown.event', 'data': {'submission_id': 1000, 'external_id': ext_id, 'email': 'buyer@example.invalid'}},
            {'event_type': 'form.completed', 'data': {'submission_id': 1000, 'external_id': ext_id, 'email': 'real@example.com'}},
            {'event_type': 'form.completed', 'data': {'submission_id': 0, 'external_id': ext_id, 'email': 'buyer@example.invalid'}},
        ):
            with self.assertRaises(ValidationError):
                verify_webhook_event(headers={'X-DocuSeal-Webhook-Secret': secret}, raw_body=json.dumps(bad_payload), expected_secret=secret)

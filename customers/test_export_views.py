# SPDX-License-Identifier: MPL-2.0
import hashlib
import json
from unittest.mock import patch
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from .test_export import CustomerExportTests
from .models import CustomerExportEvent


@override_settings(DEBUG=True, CUSTOMER_ACTIVITY_DEMO_ENABLED=True)
class CustomerExportViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CustomerExportTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.users['owner'])
        self.review = reverse('customer_export_review')
        self.download = reverse('customer_export_download')

    def test_review_and_download_have_explicit_scope_private_headers_and_audit(self):
        review = self.client.get(self.review)
        self.assertContains(review, 'not a complete backup')
        self.assertContains(review, 'not encrypted')
        self.assertContains(review, 'multiple database queries')
        self.assertFalse(CustomerExportEvent.objects.exists())
        response = self.client.post(self.download, {'dealership_id': self.other.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        data = json.loads(response.content)
        self.assertEqual(data['dealership_id'], self.dealer.pk)
        self.assertEqual({r['id'] for r in data['customers']}, {self.customer.pk, self.second.pk})
        self.assertNotIn('FOREIGN-PRIVATE', response.content.decode())
        event = CustomerExportEvent.objects.get()
        self.assertEqual((event.actor_id, event.dealership_id), (self.users['owner'].pk, self.dealer.pk))
        self.assertEqual(event.sha256, hashlib.sha256(response.content).hexdigest())
        self.assertEqual(event.byte_size, len(response.content))
        self.assertNotIn('Synthetic Buyer', str(event.__dict__))

    def test_roles_gates_and_methods(self):
        for user in ('staff', 'viewer'):
            self.client.force_login(self.users[user])
            self.assertEqual(self.client.get(self.review).status_code, 403)
            self.assertEqual(self.client.post(self.download).status_code, 403)
        self.client.force_login(self.users['foreign'])
        response = self.client.post(self.download, {'dealership_id': self.dealer.pk})
        self.assertEqual(json.loads(response.content)['dealership_id'], self.other.pk)
        self.client.force_login(self.users['owner'])
        for setting in ({'DEBUG': False}, {'CUSTOMER_ACTIVITY_DEMO_ENABLED': False}):
            with override_settings(**setting):
                self.assertEqual(self.client.get(self.review).status_code, 403)
                self.assertEqual(self.client.post(self.download).status_code, 403)
        self.assertEqual(self.client.get(self.download).status_code, 405)
        self.assertEqual(self.client.head(self.download).status_code, 405)

    def test_anonymous_csrf_and_private_error_responses(self):
        self.client.logout()
        response = self.client.post(self.download)
        self.assertEqual(response.status_code, 302)
        self.assertIn('no-store', response['Cache-Control'])
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.users['owner'])
        self.assertEqual(strict.post(self.download).status_code, 403)
        self.assertFalse(CustomerExportEvent.objects.exists())

    def test_failed_audit_or_limit_never_returns_file(self):
        with patch('customers.export_views.CustomerExportEvent.objects.create', side_effect=DatabaseError('synthetic failure')):
            response = self.client.post(self.download)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('Content-Disposition', response)
            self.assertNotIn('Synthetic', response.content.decode())
        with patch('customers.export_views.MAX_JSON_BYTES', 1):
            response = self.client.post(self.download)
            self.assertEqual(response.status_code, 409)
            self.assertNotIn('Content-Disposition', response)
        with patch('customers.export.MAX_EVENTS', 0):
            self.assertEqual(self.client.post(self.download).status_code, 409)
        self.assertFalse(CustomerExportEvent.objects.exists())

    def test_audit_is_immutable_and_rejects_foreign_actor(self):
        self.client.post(self.download)
        event = CustomerExportEvent.objects.get()
        for action in ('update', 'delete'):
            with self.subTest(action=action), self.assertRaises(DatabaseError), transaction.atomic():
                qs = CustomerExportEvent.objects.filter(pk=event.pk)
                qs.update(sha256='changed') if action == 'update' else qs.delete()
        with self.assertRaises(DatabaseError), transaction.atomic():
            CustomerExportEvent.objects.create(dealership=self.dealer, actor=self.users['foreign'], format_version='test', sha256='0'*64, byte_size=1)

    def test_customer_download_contains_only_prior_audit_events(self):
        first = self.client.post(self.download)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(json.loads(first.content)['customer_export_events'], [])
        event = CustomerExportEvent.objects.get(dealership=self.dealer)
        second = self.client.post(self.download)
        self.assertEqual(second.status_code, 200)
        events = json.loads(second.content)['customer_export_events']
        self.assertEqual([row['id'] for row in events], [event.pk])
        self.assertEqual(events[0]['sha256'], hashlib.sha256(first.content).hexdigest())
        self.assertEqual(events[0]['byte_size'], len(first.content))
        self.assertEqual(CustomerExportEvent.objects.filter(dealership=self.dealer).count(), 2)
        with patch('customers.export.MAX_EXPORT_EVENTS', 1):
            failed = self.client.post(self.download)
        self.assertEqual(failed.status_code, 409)
        self.assertNotIn('Content-Disposition', failed)
        self.assertEqual(CustomerExportEvent.objects.filter(dealership=self.dealer).count(), 2)

    def test_download_preserves_mock_history_after_simulator_is_disabled(self):
        from uuid import uuid4
        from .message_simulator import submit_mock, record_mock_event
        with override_settings(DEMO_MESSAGE_SIMULATOR_ENABLED=True):
            key = uuid4()
            submission, _ = submit_mock(dealership_id=self.dealer.pk, actor=self.users['staff'],
                submission_id=key, recipient_label='mock-recipient-alpha', scenario='mock-follow-up')
            event, _ = record_mock_event(dealership_id=self.dealer.pk, actor=self.users['staff'],
                submission_id=key, event_id=uuid4(), label='mock-delivered')
        with override_settings(DEMO_MESSAGE_SIMULATOR_ENABLED=False):
            response = self.client.post(self.download)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['format'], 'railet-synthetic-customers-v3')
        self.assertEqual([row['id'] for row in data['mock_message_submissions']], [submission.pk])
        self.assertEqual([row['id'] for row in data['mock_message_events']], [event.pk])
        self.assertEqual(CustomerExportEvent.objects.get().sha256, hashlib.sha256(response.content).hexdigest())

# SPDX-License-Identifier: MPL-2.0
import json
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.utils import timezone
from core.models import Dealership, Membership
from .export import CustomerExportTooLarge, FORMAT_VERSION, export_customers
from .models import Customer, CustomerActivity, CustomerEvent, CustomerExportEvent


@override_settings(DEBUG=True, CUSTOMER_ACTIVITY_DEMO_ENABLED=True)
class CustomerExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealership.objects.create(name='Synthetic dealership')
        cls.other = Dealership.objects.create(name='Other dealership')
        cls.users = {}
        for label, role, dealer in [('owner', 'owner', cls.dealer), ('staff', 'staff', cls.dealer),
                                    ('viewer', 'viewer', cls.dealer), ('foreign', 'owner', cls.other)]:
            user = get_user_model().objects.create_user('customer-export-' + label)
            Membership.objects.create(user=user, dealership=dealer, role=role)
            cls.users[label] = user
        cls.customer = Customer.objects.create(dealership=cls.dealer, first_name='Synthetic', last_name='Buyer',
            email='synthetic@example.invalid', lead_stage='', city='Example', address_line2='')
        cls.second = Customer.objects.create(dealership=cls.dealer, first_name='Another', last_name='Synthetic')
        cls.foreign = Customer.objects.create(dealership=cls.other, first_name='FOREIGN-PRIVATE', last_name='Synthetic')
        cls.activity = CustomerActivity.objects.create(customer=cls.customer, kind='follow_up', detail='=synthetic text',
            created_by=cls.users['staff'], assigned_to=cls.users['staff'], creation_key=uuid4(), due_at=None)
        cls.event = CustomerEvent.objects.create(customer=cls.customer, actor=cls.users['staff'],
            changes={'action': 'activity_updated', 'before': {'detail': 'old'}, 'after': {'detail': '=synthetic text'}, 'unknown': None})
        CustomerActivity.objects.create(customer=cls.foreign, kind='note', detail='FOREIGN-PRIVATE-ACTIVITY',
            created_by=cls.users['foreign'], creation_key=uuid4())
        CustomerEvent.objects.create(customer=cls.foreign, actor=cls.users['foreign'], changes={'detail': 'FOREIGN-PRIVATE-EVENT'})

    def export(self, actor=None, dealer=None):
        return export_customers(dealership_id=(dealer or self.dealer).pk, actor=actor or self.users['owner'])

    def test_all_customer_owned_records_and_history_are_scoped_and_serializable(self):
        data = self.export()
        self.assertEqual(data['format'], FORMAT_VERSION)
        self.assertEqual({x['id'] for x in data['customers']}, {self.customer.pk, self.second.pk})
        self.assertEqual([x['id'] for x in data['activities']], [self.activity.pk])
        self.assertEqual([x['id'] for x in data['events']], [self.event.pk])
        customer = next(x for x in data['customers'] if x['id'] == self.customer.pk)
        self.assertEqual(customer['lead_stage'], '')
        self.assertEqual(customer['address_line2'], '')
        activity = data['activities'][0]
        self.assertIsNone(activity['due_at'])
        self.assertIsNone(activity['completed_by_id'])
        self.assertEqual(activity['assigned_to_id'], self.users['staff'].pk)
        self.assertEqual(activity['creation_key'], str(self.activity.creation_key))
        self.assertEqual(activity['detail'], '=synthetic text')
        event = data['events'][0]
        self.assertEqual(event['changes'], self.event.changes)
        self.assertEqual(event['actor_id'], self.users['staff'].pk)
        self.assertIn('not guaranteed', data['consistency'])
        self.assertNotIn('FOREIGN-PRIVATE', json.dumps(data))
        self.assertEqual(data['exported_by_user_id'], self.users['owner'].pk)

    def test_owner_only_and_dealership_scope(self):
        for actor in (self.users['staff'], self.users['viewer'], self.users['foreign'], AnonymousUser()):
            with self.subTest(actor=str(actor)), self.assertRaises(PermissionDenied):
                self.export(actor=actor)
        with self.assertRaises(PermissionDenied):
            self.export(dealer=self.other)
        self.users['owner'].is_active = False
        self.users['owner'].save(update_fields=['is_active'])
        with self.assertRaises(PermissionDenied):
            self.export()

    def test_synthetic_gates(self):
        for overrides in ({'DEBUG': False}, {'CUSTOMER_ACTIVITY_DEMO_ENABLED': False}):
            with self.subTest(overrides=overrides), override_settings(**overrides), self.assertRaises(PermissionDenied):
                self.export()

    def test_excess_records_fail_without_partial_result(self):
        for limit in ('MAX_CUSTOMERS', 'MAX_ACTIVITIES', 'MAX_EVENTS'):
            with self.subTest(limit=limit), patch('customers.export.' + limit, 0), self.assertRaises(CustomerExportTooLarge):
                self.export()

    def test_current_activity_and_multiple_events_are_all_included(self):
        activity = self.activity
        activity.completed_at = timezone.now()
        activity.completed_by = self.users['owner']
        activity.revision = 2
        activity.save(update_fields=['completed_at', 'completed_by', 'revision'])
        second_event = CustomerEvent.objects.create(customer=self.customer, actor=self.users['owner'], changes={'action': 'activity_completed', 'activity_id': activity.pk, 'revision': 2})
        result = self.export()
        self.assertEqual(result['activities'][0]['revision'], 2)
        self.assertEqual(result['activities'][0]['completed_by_id'], self.users['owner'].pk)
        self.assertEqual([event['id'] for event in result['events']], [self.event.pk, second_event.pk])

    def test_prior_export_audit_is_versioned_scoped_complete_and_bounded(self):
        local = CustomerExportEvent.objects.create(dealership=self.dealer, actor=self.users['owner'],
            format_version='railet-synthetic-customers-v2', sha256='c' * 64, byte_size=456)
        CustomerExportEvent.objects.create(dealership=self.other, actor=self.users['foreign'],
            format_version='foreign-private', sha256='d' * 64, byte_size=999)
        data = self.export()
        self.assertEqual(data['format'], 'railet-synthetic-customers-v3')
        self.assertTrue({'customers', 'activities', 'events', 'mock_message_submissions', 'mock_message_events'} <= data.keys())
        self.assertEqual(data['customer_export_events'], [{
            'id': local.pk, 'dealership_id': self.dealer.pk, 'actor_id': self.users['owner'].pk,
            'created_at': local.created_at.isoformat(), 'format_version': 'railet-synthetic-customers-v2',
            'sha256': 'c' * 64, 'byte_size': 456,
        }])
        self.assertNotIn('foreign-private', json.dumps(data))
        with self.assertRaises(PermissionDenied):
            self.export(actor=self.users['staff'])
        with patch('customers.export.MAX_EXPORT_EVENTS', 0), self.assertRaises(CustomerExportTooLarge):
            self.export()

    def test_mock_history_is_scoped_and_retained_when_simulator_disabled(self):
        from .message_simulator import submit_mock, record_mock_event
        from .models import MockMessageSubmission, MockMessageEvent
        with override_settings(DEMO_MESSAGE_SIMULATOR_ENABLED=True):
            key = uuid4()
            submission, _ = submit_mock(dealership_id=self.dealer.pk, actor=self.users['staff'],
                submission_id=key, recipient_label='mock-recipient-alpha', scenario='mock-follow-up')
            event_key = uuid4()
            event, _ = record_mock_event(dealership_id=self.dealer.pk, actor=self.users['staff'],
                submission_id=key, event_id=event_key, label='mock-delivered')
            foreign_key = uuid4()
            foreign, _ = submit_mock(dealership_id=self.other.pk, actor=self.users['foreign'],
                submission_id=foreign_key, recipient_label='mock-recipient-beta', scenario='mock-appointment')
            record_mock_event(dealership_id=self.other.pk, actor=self.users['foreign'],
                submission_id=foreign_key, event_id=uuid4(), label='mock-failed')
        with override_settings(DEMO_MESSAGE_SIMULATOR_ENABLED=False):
            result = self.export()
        self.assertEqual(result['format'], 'railet-synthetic-customers-v3')
        self.assertEqual([row['id'] for row in result['mock_message_submissions']], [submission.pk])
        self.assertEqual([row['id'] for row in result['mock_message_events']], [event.pk])
        saved = result['mock_message_submissions'][0]
        observation = result['mock_message_events'][0]
        self.assertEqual(set(saved), {f.attname for f in MockMessageSubmission._meta.concrete_fields})
        self.assertEqual(set(observation), {f.attname for f in MockMessageEvent._meta.concrete_fields})
        self.assertEqual(saved['submission_id'], str(key))
        self.assertEqual(saved['actor_id'], self.users['staff'].pk)
        self.assertEqual(saved['recipient_label'], 'mock-recipient-alpha')
        self.assertEqual(saved['created_at'], submission.created_at.isoformat())
        self.assertEqual(observation['event_id'], str(event_key))
        self.assertEqual(observation['submission_id'], submission.pk)
        self.assertEqual(observation['created_at'], event.created_at.isoformat())
        self.assertEqual(observation['label'], 'mock-delivered')
        self.assertNotIn(str(foreign_key), json.dumps(result))
        self.assertNotIn(foreign.pk, [row['id'] for row in result['mock_message_submissions']])
        self.assertIn('not real delivery or consent', result['scope'])
        for limit in ('MAX_MOCK_SUBMISSIONS', 'MAX_MOCK_EVENTS'):
            with self.subTest(limit=limit), patch('customers.export.' + limit, 0), self.assertRaises(CustomerExportTooLarge):
                self.export()

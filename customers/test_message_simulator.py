# SPDX-License-Identifier: MPL-2.0
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.http import Http404
from django.test import TestCase, override_settings
from core.models import Dealership, Membership
from .message_simulator import SimulatorConflict, submit_mock, record_mock_event, mock_status
from .models import MockMessageSubmission, MockMessageEvent


@override_settings(DEBUG=True, CUSTOMER_ACTIVITY_DEMO_ENABLED=True, DEMO_MESSAGE_SIMULATOR_ENABLED=True)
class MockMessageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealership.objects.create(name='Synthetic simulator')
        cls.other = Dealership.objects.create(name='Other synthetic')
        cls.users = {}
        for name, role, dealer in [('owner','owner',cls.dealer), ('staff','staff',cls.dealer),
                                    ('viewer','viewer',cls.dealer), ('foreign','owner',cls.other)]:
            user = get_user_model().objects.create_user('sim-' + name)
            Membership.objects.create(user=user, dealership=dealer, role=role)
            cls.users[name] = user

    def setUp(self):
        self.key = uuid4()
        self.args = dict(dealership_id=self.dealer.pk, actor=self.users['staff'], submission_id=self.key,
                         recipient_label='mock-recipient-alpha', scenario='mock-follow-up')

    def event(self, label, event_id=None, **changes):
        args = dict(dealership_id=self.dealer.pk, actor=self.users['staff'], submission_id=self.key,
                    event_id=event_id or uuid4(), label=label)
        return record_mock_event(**(args | changes))

    def status(self):
        return mock_status(dealership_id=self.dealer.pk, actor=self.users['staff'], submission_id=self.key)

    def test_submissions_and_events_are_idempotent_and_conflicting_ids_are_rejected(self):
        submission, created = submit_mock(**self.args)
        self.assertTrue(created)
        self.assertEqual(submit_mock(**self.args), (submission, False))
        for change in ({'scenario':'mock-appointment'}, {'recipient_label':'mock-recipient-beta'}, {'actor':self.users['owner']}):
            with self.subTest(change=change), self.assertRaises(SimulatorConflict): submit_mock(**(self.args | change))
        event_id = uuid4(); event, created = self.event('mock-accepted', event_id)
        self.assertTrue(created)
        self.assertEqual(self.event('mock-accepted', event_id), (event, False))
        with self.assertRaises(SimulatorConflict): self.event('mock-failed', event_id)
        with self.assertRaises(SimulatorConflict): self.event('mock-accepted', event_id, actor=self.users['owner'])
        self.assertEqual(MockMessageSubmission.objects.count(), 1)
        self.assertEqual(MockMessageEvent.objects.count(), 1)

    def test_out_of_order_terminal_observations_do_not_regress_or_disappear(self):
        submit_mock(**self.args)
        self.assertEqual(self.status(), 'mock-submitted')
        self.event('mock-delivered'); self.assertEqual(self.status(), 'mock-delivered')
        self.event('mock-accepted'); self.assertEqual(self.status(), 'mock-delivered')
        self.event('mock-failed'); self.assertEqual(self.status(), 'mock-conflict')
        self.event('mock-accepted'); self.assertEqual(self.status(), 'mock-conflict')
        self.assertEqual(MockMessageEvent.objects.count(), 4)

    def test_no_phone_free_text_or_customer_data_is_accepted(self):
        for recipient in ('+13055551234', '3055551234', 'mock-recipient-3055551234', '', 'real person'):
            with self.subTest(recipient=recipient), self.assertRaises(ValidationError): submit_mock(**(self.args | {'recipient_label':recipient}))
        with self.assertRaises(ValidationError): submit_mock(**(self.args | {'scenario':'call 3055551234'}))
        with self.assertRaises(ValidationError): submit_mock(**(self.args | {'submission_id':'3055551234'}))
        with self.assertRaises(TypeError): submit_mock(**self.args, phone='+13055551234')
        with self.assertRaises(TypeError): submit_mock(**self.args, message='real message')
        self.assertFalse(MockMessageSubmission.objects.exists())

    def test_isolation_roles_gates_and_disabled_by_default(self):
        submit_mock(**self.args)
        for actor in (self.users['viewer'], self.users['foreign'], AnonymousUser()):
            with self.subTest(actor=str(actor)), self.assertRaises(PermissionDenied):
                submit_mock(**(self.args | {'actor':actor}))
        with self.assertRaises(Http404):
            self.event('mock-accepted', dealership_id=self.other.pk, actor=self.users['foreign'])
        self.users['staff'].is_active = False; self.users['staff'].save(update_fields=['is_active'])
        with self.assertRaises(PermissionDenied): self.status()
        self.users['staff'].is_active = True; self.users['staff'].save(update_fields=['is_active'])
        for setting in ('DEBUG', 'CUSTOMER_ACTIVITY_DEMO_ENABLED', 'DEMO_MESSAGE_SIMULATOR_ENABLED'):
            with self.subTest(setting=setting), override_settings(**{setting:False}), self.assertRaises(PermissionDenied): self.status()
        with override_settings(DEMO_MESSAGE_SIMULATOR_ENABLED=False), self.assertRaises(PermissionDenied):
            self.event('mock-delivered')

    def test_atomic_failure_and_immutable_history(self):
        submission, _ = submit_mock(**self.args)
        with patch('customers.message_simulator.MockMessageEvent.objects.create', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError): self.event('mock-accepted')
        self.assertFalse(MockMessageEvent.objects.exists())
        event, _ = self.event('mock-accepted')
        for model, pk, field, value in ((MockMessageSubmission, submission.pk, 'scenario', 'mock-appointment'),
                                        (MockMessageEvent, event.pk, 'label', 'mock-failed')):
            for operation in ('update', 'delete'):
                with self.subTest(model=model.__name__, operation=operation), self.assertRaises(DatabaseError), transaction.atomic():
                    query = model.objects.filter(pk=pk)
                    query.update(**{field:value}) if operation == 'update' else query.delete()

    def test_database_constraints_reject_real_recipient_and_unrecognized_event(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            MockMessageSubmission.objects.create(dealership=self.dealer, actor=self.users['owner'],
                submission_id=uuid4(), recipient_label='+13055551234', scenario='mock-follow-up')
        submission, _ = submit_mock(**self.args)
        with self.assertRaises(DatabaseError), transaction.atomic():
            MockMessageEvent.objects.create(submission=submission, actor=self.users['staff'],
                event_id=uuid4(), label='real-message')
        self.assertFalse(MockMessageEvent.objects.exists())

    def test_identical_local_id_in_another_dealership_stays_isolated(self):
        original, _ = submit_mock(**self.args)
        foreign, _ = submit_mock(**(self.args | {'dealership_id': self.other.pk, 'actor': self.users['foreign']}))
        self.event('mock-delivered')
        self.assertNotEqual(original.pk, foreign.pk)
        self.assertEqual(mock_status(dealership_id=self.other.pk, actor=self.users['foreign'], submission_id=self.key), 'mock-submitted')
        self.assertEqual(self.status(), 'mock-delivered')

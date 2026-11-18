# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from core.models import Dealership, Membership
from .message_simulator import SimulatorConflict, submit_mock, record_mock_event, mock_status
from .models import MockMessageEvent, MockMessageSubmission


@skipUnless(connection.vendor == 'postgresql', 'Row-lock concurrency requires PostgreSQL')
@override_settings(DEBUG=True, CUSTOMER_ACTIVITY_DEMO_ENABLED=True, DEMO_MESSAGE_SIMULATOR_ENABLED=True)
class MockMessageConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.dealer = Dealership.objects.create(name='Synthetic simulator race')
        self.staff = get_user_model().objects.create_user('simulation-race-staff')
        self.owner = get_user_model().objects.create_user('simulation-race-owner')
        Membership.objects.create(user=self.staff, dealership=self.dealer, role='staff')
        Membership.objects.create(user=self.owner, dealership=self.dealer, role='owner')
        self.key = uuid4()

    def race(self, operations):
        barrier = Barrier(len(operations))
        def run(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    return operation()
                except SimulatorConflict:
                    return 'conflict'
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            return list(pool.map(run, operations))

    def test_simultaneous_submission_retry_saves_once(self):
        def submit():
            obj, created = submit_mock(dealership_id=self.dealer.pk, actor=self.staff, submission_id=self.key,
                recipient_label='mock-recipient-alpha', scenario='mock-follow-up')
            return obj.pk, created
        results = self.race([submit, submit])
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sorted(item[1] for item in results), [False, True])
        self.assertEqual(MockMessageSubmission.objects.count(), 1)

    def test_different_actors_cannot_claim_same_submission(self):
        def submit(actor):
            def run():
                return submit_mock(dealership_id=self.dealer.pk, actor=actor, submission_id=self.key,
                    recipient_label='mock-recipient-alpha', scenario='mock-follow-up')[0].pk
            return run
        results = self.race([submit(self.owner), submit(self.staff)])
        self.assertEqual(results.count('conflict'), 1)
        self.assertEqual(MockMessageSubmission.objects.count(), 1)

    def test_simultaneous_event_retry_and_conflict_are_serialized(self):
        submit_mock(dealership_id=self.dealer.pk, actor=self.owner, submission_id=self.key,
                    recipient_label='mock-recipient-alpha', scenario='mock-follow-up')
        event_key = uuid4()
        def record(actor, label):
            def run():
                event, created = record_mock_event(dealership_id=self.dealer.pk, actor=actor,
                    submission_id=self.key, event_id=event_key, label=label)
                return event.pk, created
            return run
        results = self.race([record(self.owner, 'mock-delivered'), record(self.owner, 'mock-delivered')])
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sorted(item[1] for item in results), [False, True])
        results = self.race([record(self.owner, 'mock-delivered'), record(self.staff, 'mock-failed')])
        self.assertEqual(results.count('conflict'), 1)
        self.assertEqual(MockMessageEvent.objects.count(), 1)
        self.assertEqual(mock_status(dealership_id=self.dealer.pk, actor=self.owner, submission_id=self.key), 'mock-delivered')

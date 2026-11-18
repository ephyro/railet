# SPDX-License-Identifier: MPL-2.0
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from core.models import Dealership, Membership
from .export import FORMAT_VERSION, FeedbackExportTooLarge, authorize_feedback_export, export_feedback
from .models import FeedbackReport


@override_settings(DEBUG=True)
class FeedbackExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealership.objects.create(name='Synthetic feedback export dealer')
        cls.other = Dealership.objects.create(name='Other feedback export dealer')
        cls.users = {}
        for label, role, dealer in [
            ('owner', 'owner', cls.dealer),
            ('staff', 'staff', cls.dealer),
            ('viewer', 'viewer', cls.dealer),
            ('foreign', 'owner', cls.other),
        ]:
            user = get_user_model().objects.create_user('fb-export-' + label)
            Membership.objects.create(user=user, dealership=dealer, role=role)
            cls.users[label] = user

        cls.staff_report = FeedbackReport.objects.create(
            dealership=cls.dealer, author=cls.users['staff'], submission_key=uuid4(),
            kind='bug', area='inventory', subject='=Synthetic subject',
            expected='Expected synthetic behavior.', actual='Actual <script>synthetic</script> text.',
        )
        cls.viewer_report = FeedbackReport.objects.create(
            dealership=cls.dealer, author=cls.users['viewer'], submission_key=uuid4(),
            kind='idea', area='customers', subject='Viewer synthetic suggestion',
            expected='Clearer filter.', actual='Current filter works.',
        )
        cls.foreign_report = FeedbackReport.objects.create(
            dealership=cls.other, author=cls.users['foreign'], submission_key=uuid4(),
            kind='bug', area='deals', subject='FOREIGN-PRIVATE-SUBJECT',
            expected='FOREIGN-PRIVATE-EXPECTED', actual='FOREIGN-PRIVATE-ACTUAL',
        )

    def export(self, actor=None, dealer=None):
        return export_feedback(dealership_id=(dealer or self.dealer).pk, actor=actor or self.users['owner'])

    def test_all_dealership_reports_and_unredacted_text_are_scoped_and_serializable(self):
        data = self.export()
        serialized = json.dumps(data)
        self.assertEqual(data['format'], FORMAT_VERSION)
        self.assertTrue(data['synthetic_only'])
        self.assertTrue(data['unredacted_free_text'])
        self.assertFalse(data['delivery_audited'])
        self.assertEqual(data['dealership_id'], self.dealer.pk)
        self.assertEqual(data['exported_by_user_id'], self.users['owner'].pk)
        self.assertIn('unredacted', data['scope'])
        self.assertIn('no HTTP endpoint or delivery audit event', data['scope'])
        self.assertIn('not a complete dealership backup', data['scope'])
        self.assertNotIn('FOREIGN-PRIVATE', serialized)

        self.assertEqual([r['id'] for r in data['reports']], [self.staff_report.pk, self.viewer_report.pk])
        first, second = data['reports']
        self.assertEqual(first['author_id'], self.users['staff'].pk)
        self.assertEqual(first['submission_key'], str(self.staff_report.submission_key))
        self.assertEqual(first['kind'], 'bug')
        self.assertEqual(first['area'], 'inventory')
        self.assertEqual(first['subject'], '=Synthetic subject')
        self.assertEqual(first['expected'], 'Expected synthetic behavior.')
        self.assertEqual(first['actual'], 'Actual <script>synthetic</script> text.')
        self.assertEqual(second['author_id'], self.users['viewer'].pk)

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

    def test_synthetic_development_gate(self):
        with override_settings(DEBUG=False), self.assertRaises(PermissionDenied):
            self.export()

    def test_excess_records_or_bytes_fail_closed_without_partial_result(self):
        for limit in ('MAX_REPORTS', 'MAX_JSON_BYTES'):
            with self.subTest(limit=limit), patch('feedback.export.' + limit, 0), self.assertRaises(FeedbackExportTooLarge):
                self.export()


@skipUnless(connection.vendor == 'postgresql', 'Requires PostgreSQL row locking')
@override_settings(DEBUG=True)
class FeedbackExportLockOrderTests(TransactionTestCase):
    def test_export_waits_on_dealership_before_locking_membership(self):
        dealer = Dealership.objects.create(name='Synthetic feedback lock dealer')
        user = get_user_model().objects.create_user('synthetic-feedback-lock-owner')
        Membership.objects.create(user=user, dealership=dealer, role='owner')
        started = Event()
        backend = []

        def authorize():
            close_old_connections()
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT pg_backend_pid()')
                        backend.append(cursor.fetchone()[0])
                    started.set()
                    return authorize_feedback_export(dealership_id=dealer.pk, actor=user).pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Dealership.objects.select_for_update().get(pk=dealer.pk)
                result = pool.submit(authorize)
                self.assertTrue(started.wait(10))
                deadline = monotonic() + 10
                while True:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s', [backend[0]])
                        row = cursor.fetchone()
                    if row and row[0] == 'Lock':
                        break
                    if monotonic() >= deadline:
                        self.fail('Feedback export did not wait on the dealership lock')
                    sleep(0.02)
                # Membership-first ordering holds this row while waiting above.
                Membership.objects.select_for_update(nowait=True).get(user=user)
            self.assertIsNotNone(result.result(timeout=15))

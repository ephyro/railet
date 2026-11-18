# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest import skipUnless
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import Client, TransactionTestCase
from django.urls import reverse

from core.models import Dealership, Membership
from .models import FeedbackReport


@skipUnless(connection.vendor == 'postgresql', 'Row locking requires PostgreSQL')
class FeedbackConfirmRaceTests(TransactionTestCase):
    def test_simultaneous_confirmation_preserves_one_private_report(self):
        dealer = Dealership.objects.create(name='Synthetic duplicate feedback dealer')
        user = get_user_model().objects.create_user('synthetic-duplicate-feedback')
        Membership.objects.create(user=user, dealership=dealer, role='viewer')
        client = Client()
        client.force_login(user)
        preview = client.post(reverse('feedback_create'), {
            'submission_key': str(uuid4()), 'kind': 'bug', 'area': 'inventory',
            'subject': 'Synthetic private subject', 'expected': 'Synthetic expected',
            'actual': 'Synthetic actual', 'privacy_checked': 'on',
        })
        token = preview.context['token']
        barrier = Barrier(2)

        def confirm():
            close_old_connections()
            try:
                barrier.wait(timeout=20)
                response = client.post(reverse('feedback_confirm'), {'preview_token': token, 'action': 'save'})
                return response.status_code, response.url
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result(timeout=30) for future in (pool.submit(confirm), pool.submit(confirm))]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0], 302)
        report = FeedbackReport.objects.get()
        self.assertEqual((report.dealership_id, report.author_id, report.subject), (dealer.pk, user.pk, 'Synthetic private subject'))

    def test_membership_and_activity_rechecked_after_lock_wait(self):
        dealer = Dealership.objects.create(name='Synthetic feedback race dealer')
        other = Dealership.objects.create(name='Synthetic other dealer')
        user = get_user_model().objects.create_user('synthetic-feedback-race')
        member = Membership.objects.create(user=user, dealership=dealer, role='staff')
        client = Client()
        client.force_login(user)
        for revoked in ('inactive', 'foreign', 'removed', 'invalid_role'):
            with self.subTest(revoked=revoked):
                preview = client.post(reverse('feedback_create'), {
                    'submission_key': str(uuid4()), 'kind': 'bug', 'area': 'inventory',
                    'subject': 'Synthetic feedback', 'expected': 'Synthetic expected',
                    'actual': 'Synthetic actual', 'privacy_checked': 'on',
                })
                token = preview.context['token']
                attempted = Event()

                def confirm():
                    close_old_connections()
                    try:
                        def signal_lock(execute, sql, params, many, context):
                            if 'core_membership' in sql and 'FOR UPDATE' in sql:
                                attempted.set()
                            return execute(sql, params, many, context)
                        with connection.execute_wrapper(signal_lock):
                            return client.post(reverse('feedback_confirm'), {'preview_token': token, 'action': 'save'}).status_code
                    finally:
                        close_old_connections()

                with ThreadPoolExecutor(max_workers=1) as pool:
                    with transaction.atomic():
                        if revoked == 'inactive':
                            get_user_model().objects.select_for_update().get(pk=user.pk)
                        else:
                            Membership.objects.select_for_update().get(pk=member.pk)
                        future = pool.submit(confirm)
                        self.assertTrue(attempted.wait(timeout=20))
                        if revoked == 'inactive':
                            get_user_model().objects.filter(pk=user.pk).update(is_active=False)
                        elif revoked == 'foreign':
                            Membership.objects.filter(pk=member.pk).update(dealership=other)
                        elif revoked == 'removed':
                            Membership.objects.filter(pk=member.pk).delete()
                        else:
                            Membership.objects.filter(pk=member.pk).update(role='invalid')
                    self.assertEqual(future.result(timeout=20), 403)
                self.assertEqual(FeedbackReport.objects.count(), 0)
                get_user_model().objects.filter(pk=user.pk).update(is_active=True)
                member, _ = Membership.objects.update_or_create(user=user, defaults={'dealership': dealer, 'role': 'staff'})

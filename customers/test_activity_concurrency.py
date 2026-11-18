# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse

from core.models import Dealership, Membership
from .models import Customer, CustomerActivity, CustomerEvent


@skipUnless(connection.vendor == 'postgresql', 'Row locking requires PostgreSQL')
@override_settings(CUSTOMER_ACTIVITY_DEMO_ENABLED=True)
class ActivityAuthorizationRaceTests(TransactionTestCase):
    def test_edit_and_completion_recheck_actor_after_role_or_activity_wait(self):
        dealer = Dealership.objects.create(name='Synthetic activity update dealer')
        actor = get_user_model().objects.create_user('activity-update-actor')
        member = Membership.objects.create(user=actor, dealership=dealer, role='staff')
        customer = Customer.objects.create(dealership=dealer, first_name='Synthetic', last_name='Buyer')
        activity = CustomerActivity.objects.create(customer=customer, created_by=actor, kind='follow_up',
                                                   detail='Synthetic task', creation_key=uuid4())
        client = Client()
        client.force_login(actor)
        for operation in ('edit', 'complete'):
            for revocation in ('role', 'inactive'):
                with self.subTest(operation=operation, revocation=revocation):
                    attempted = Event()
                    url = reverse('customer_activity_' + operation, args=[customer.pk, activity.pk])
                    data = {'revision': 1, 'detail': activity.detail, 'assigned_to': '', 'due_at': ''}

                    def post():
                        close_old_connections()
                        try:
                            def signal_lock(execute, sql, params, many, context):
                                if 'core_membership' in sql and 'FOR UPDATE' in sql and params and params[-1] == actor.pk:
                                    attempted.set()
                                return execute(sql, params, many, context)
                            with connection.execute_wrapper(signal_lock):
                                return client.post(url, data).status_code
                        finally:
                            close_old_connections()

                    with ThreadPoolExecutor(max_workers=1) as pool:
                        with transaction.atomic():
                            if revocation == 'role':
                                Membership.objects.select_for_update().get(pk=member.pk)
                            else:
                                get_user_model().objects.select_for_update().get(pk=actor.pk)
                            future = pool.submit(post)
                            self.assertTrue(attempted.wait(timeout=20))
                            if revocation == 'role':
                                Membership.objects.filter(pk=member.pk).update(role='viewer')
                            else:
                                get_user_model().objects.filter(pk=actor.pk).update(is_active=False)
                        self.assertEqual(future.result(timeout=20), 403)
                    activity.refresh_from_db()
                    self.assertEqual((activity.revision, activity.completed_at, CustomerEvent.objects.count()), (1, None, 0))
                    Membership.objects.filter(pk=member.pk).update(role='staff')
                    get_user_model().objects.filter(pk=actor.pk).update(is_active=True)

    def test_actor_and_assignee_rechecked_after_identity_lock_wait(self):
        dealer = Dealership.objects.create(name='Synthetic activity race dealer')
        actor = get_user_model().objects.create_user('activity-race-actor')
        assignee = get_user_model().objects.create_user('activity-race-assignee')
        members = {user.pk: Membership.objects.create(user=user, dealership=dealer, role='staff') for user in (actor, assignee)}
        customer = Customer.objects.create(dealership=dealer, first_name='Synthetic', last_name='Buyer')
        client = Client()
        client.force_login(actor)
        url = reverse('customer_activity_create', args=[customer.pk])
        for user in (actor, assignee):
            for revocation in ('role', 'inactive'):
                with self.subTest(user=user.pk, revocation=revocation):
                    attempted = Event()

                    def post():
                        close_old_connections()
                        try:
                            def signal_lock(execute, sql, params, many, context):
                                if 'core_membership' in sql and 'FOR UPDATE' in sql and params and params[-1] == user.pk:
                                    attempted.set()
                                return execute(sql, params, many, context)
                            with connection.execute_wrapper(signal_lock):
                                return client.post(url, {'kind': 'follow_up', 'detail': 'Synthetic task',
                                                         'creation_key': str(uuid4()), 'assigned_to': assignee.pk}).status_code
                        finally:
                            close_old_connections()

                    with ThreadPoolExecutor(max_workers=1) as pool:
                        with transaction.atomic():
                            if revocation == 'role':
                                Membership.objects.select_for_update().get(pk=members[user.pk].pk)
                            else:
                                get_user_model().objects.select_for_update().get(pk=user.pk)
                            future = pool.submit(post)
                            self.assertTrue(attempted.wait(timeout=20))
                            if revocation == 'role':
                                Membership.objects.filter(pk=members[user.pk].pk).update(role='viewer')
                            else:
                                get_user_model().objects.filter(pk=user.pk).update(is_active=False)
                        self.assertEqual(future.result(timeout=20), 403 if user.pk == actor.pk else 409)
                    self.assertEqual((CustomerActivity.objects.count(), CustomerEvent.objects.count()), (0, 0))
                    Membership.objects.filter(pk=members[user.pk].pk).update(role='staff')
                    get_user_model().objects.filter(pk=user.pk).update(is_active=True)

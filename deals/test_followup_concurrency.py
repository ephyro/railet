# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse

from core.models import Dealership, Membership
from customers.models import Customer
from inventory.models import Vehicle
from .models import DraftDeal, DealFollowUp, FollowUpEvent


@skipUnless(connection.vendor == 'postgresql', 'Requires PostgreSQL row locking')
class FollowUpConcurrencyTests(TransactionTestCase):
    def setUp(self):
        dealer = Dealership.objects.create(name='Synthetic concurrency dealer')
        self.user = get_user_model().objects.create_user('synthetic-followup-editor')
        Membership.objects.create(user=self.user, dealership=dealer, role='owner')
        customer = Customer.objects.create(dealership=dealer, first_name='Synthetic', last_name='Buyer')
        vehicle = Vehicle.objects.create(dealership=dealer, stock_number='RACE-FOLLOW', year=2020, make='Synthetic', model='Car')
        self.deal = DraftDeal.objects.create(dealership=dealer, buyer=customer, vehicle=vehicle)
        self.key = uuid4()
        self.data = {'title': 'Original synthetic reminder', 'detail': '', 'assigned_to': '',
                     'due_on': '', 'revision': 1, 'creation_key': str(self.key)}

    def concurrent_posts(self, url, bodies):
        ready = Barrier(2)
        def post(body):
            close_old_connections()
            try:
                client = Client()
                client.force_login(self.user)
                ready.wait(timeout=15)
                response = client.post(url, body)
                return response.status_code, response.get('Location')
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(post, bodies))

    def test_simultaneous_same_key_retries_create_one_task_and_event(self):
        results = self.concurrent_posts(reverse('followup_create', args=[self.deal.pk]), [self.data, self.data])
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0], 302)
        task = DealFollowUp.objects.get(deal=self.deal, creation_key=self.key)
        self.assertEqual(task.title, self.data['title'])
        self.assertEqual(task.revision, 1)
        self.assertEqual(list(task.events.values_list('action', flat=True)), ['created'])
        self.assertEqual(FollowUpEvent.objects.count(), 1)

    def test_simultaneous_stale_updates_preserve_winner_and_history(self):
        task = DealFollowUp.objects.create(deal=self.deal, title=self.data['title'],
                                           created_by=self.user, creation_key=self.key)
        url = reverse('followup_edit', args=[self.deal.pk, task.pk])
        results = self.concurrent_posts(url, [self.data | {'title': 'First proposed edit'},
                                              self.data | {'title': 'Second proposed edit'}])
        self.assertEqual(sorted(status for status, _ in results), [302, 409])
        task.refresh_from_db()
        self.assertIn(task.title, ('First proposed edit', 'Second proposed edit'))
        self.assertEqual(task.revision, 2)
        event = FollowUpEvent.objects.get(follow_up=task)
        self.assertEqual(event.action, 'updated')
        self.assertEqual(event.snapshot['title'], task.title)
        self.assertEqual(event.snapshot['revision'], 2)

    def test_role_and_active_changes_wait_until_save_commits(self):
        from threading import Event
        from unittest.mock import patch
        from django.db import transaction
        from .followups import snapshot
        assignee = get_user_model().objects.create_user('synthetic-assignee')
        Membership.objects.create(user=assignee, dealership=self.deal.dealership, role='staff')
        entered, release, attempted, changed = Event(), Event(), Event(), Event()

        def paused_snapshot(task):
            entered.set()
            if not release.wait(15):
                raise TimeoutError('Save did not receive release')
            return snapshot(task)

        def post():
            close_old_connections()
            try:
                client = Client(); client.force_login(self.user)
                return client.post(reverse('followup_create', args=[self.deal.pk]), self.data | {'assigned_to': assignee.pk}).status_code
            finally:
                close_old_connections()

        def revoke():
            close_old_connections()
            try:
                if not entered.wait(15): raise TimeoutError('Save did not enter')
                attempted.set()
                with transaction.atomic():
                    Membership.objects.filter(user=self.user).update(role='viewer')
                    get_user_model().objects.filter(pk=assignee.pk).update(is_active=False)
                changed.set()
            finally:
                close_old_connections()

        with patch('deals.followups.snapshot', side_effect=paused_snapshot):
            with ThreadPoolExecutor(max_workers=2) as pool:
                save = pool.submit(post); change = pool.submit(revoke)
                try:
                    self.assertTrue(attempted.wait(15))
                    self.assertFalse(changed.wait(0.5), 'Revocation bypassed save locks')
                finally:
                    release.set()
                self.assertEqual(save.result(timeout=15), 302)
                change.result(timeout=15)
        task = DealFollowUp.objects.get(deal=self.deal)
        self.assertEqual(task.assigned_to_id, assignee.pk)
        self.assertEqual(task.events.count(), 1)
        self.assertTrue(changed.is_set())

    def test_revocation_before_save_authorization_prevents_write(self):
        from django.db import transaction
        from django.core.exceptions import PermissionDenied
        from django.test import RequestFactory
        from .followups import FollowUpForm, save_form
        form = FollowUpForm(self.data, dealership=self.deal.dealership)
        self.assertTrue(form.is_valid())
        Membership.objects.filter(user=self.user).update(role='viewer')
        request = RequestFactory().post('/'); request.user = self.user
        with transaction.atomic(), self.assertRaises(PermissionDenied):
            DraftDeal.objects.select_for_update().get(pk=self.deal.pk)
            save_form(request, form, self.deal)
        self.assertFalse(DealFollowUp.objects.exists())
        self.assertFalse(FollowUpEvent.objects.exists())

    @override_settings(DEBUG=True)
    def test_foundation_export_and_followup_serialize_without_deadlock(self):
        from threading import Event
        from unittest.mock import patch
        from core.export import export_foundation
        from .followups import snapshot
        entered, release, export_started = Event(), Event(), Event()

        def pause(task):
            entered.set()
            if not release.wait(15): raise TimeoutError('Follow-up not released')
            return snapshot(task)

        def save():
            close_old_connections()
            try:
                client = Client(); client.force_login(self.user)
                return client.post(reverse('followup_create', args=[self.deal.pk]), self.data).status_code
            finally: close_old_connections()

        def export():
            close_old_connections()
            try:
                if not entered.wait(15): raise TimeoutError('Follow-up not entered')
                export_started.set()
                return export_foundation(dealership_id=self.deal.dealership_id, actor=self.user)
            finally: close_old_connections()

        with patch('deals.followups.snapshot', side_effect=pause):
            with ThreadPoolExecutor(max_workers=2) as pool:
                saved = pool.submit(save); exported = pool.submit(export)
                try:
                    self.assertTrue(export_started.wait(15))
                finally:
                    release.set()
                self.assertEqual(saved.result(timeout=15), 302)
                self.assertEqual(exported.result(timeout=15)['dealership']['id'], self.deal.dealership_id)
        self.assertEqual(DealFollowUp.objects.count(), 1)
        self.assertEqual(FollowUpEvent.objects.count(), 1)

    @override_settings(DEBUG=True)
    def test_export_rechecks_owner_after_waiting_for_dealership(self):
        from threading import Event
        from django.core.exceptions import PermissionDenied
        from django.db import transaction
        from core.export import export_foundation
        attempted = Event()

        def export():
            close_old_connections()
            try:
                attempted.set()
                try:
                    export_foundation(dealership_id=self.deal.dealership_id, actor=self.user)
                except PermissionDenied:
                    return 'denied'
                return 'allowed'
            finally: close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Dealership.objects.select_for_update().get(pk=self.deal.dealership_id)
                pending = pool.submit(export)
                self.assertTrue(attempted.wait(15))
                Membership.objects.filter(user=self.user).update(role='viewer')
            self.assertEqual(pending.result(timeout=15), 'denied')

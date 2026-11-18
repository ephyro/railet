# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest import skipUnless
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase, override_settings
from core.models import AuditEvent, Dealership, Membership
from . import test_reconditioning as references
from .models import ReconTask, VehicleCostEntry, VehicleVendor, VehicleVendorEvent
from .reconditioning import add_cost, add_task, reverse_cost, save_vendor


@skipUnless(connection.vendor == 'postgresql', 'Concurrency requires PostgreSQL')
@override_settings(RECON_DEMO_ENABLED=True)
class ReconConcurrencyTests(TransactionTestCase):
    def setUp(self):
        references.ReconTests.setUp(self)

    def race(self, functions):
        barrier = Barrier(len(functions))
        def run(function):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return function()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            return list(pool.map(run, functions))

    def test_cost_retries_and_vendor_creation_serialize(self):
        data=references.ReconTests.data(self) | {'new_vendor':'Concurrent Practice Garage'}
        def save():
            return add_cost(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, data=data).pk
        ids=self.race([save, save])
        self.assertEqual(ids[0],ids[1])
        self.assertEqual(VehicleCostEntry.objects.count(),1)
        self.assertEqual(VehicleVendor.objects.count(),1)

    def test_two_corrections_cannot_reverse_cost_twice(self):
        entry=add_cost(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, data=references.ReconTests.data(self))
        def correct():
            try:
                reverse_cost(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, entry_id=entry.pk, reason='Synthetic simultaneous correction', request_key=uuid4())
                return 'saved'
            except ValidationError:
                return 'rejected'
        self.assertCountEqual(self.race([correct,correct]),['saved','rejected'])
        self.assertEqual(VehicleCostEntry.objects.filter(kind='reversal').count(),1)

    def test_actor_and_assignee_revocation_after_parent_lock_wait(self):
        assignee = get_user_model().objects.create_user(username='concurrent-recon-assignee')
        assignee_member = Membership.objects.create(user=assignee, dealership=self.dealer, role='staff')
        for operation, target, revocation in (('task', 'actor', 'role'), ('task', 'actor', 'inactive'),
                                              ('task', 'assignee', 'role'), ('task', 'assignee', 'inactive'),
                                              ('vendor', 'actor', 'role')):
            with self.subTest(operation=operation, target=target, revocation=revocation):
                attempted = Event()

                def run():
                    close_old_connections()
                    try:
                        def signal_lock(execute, sql, params, many, context):
                            if 'core_dealership' in sql and 'FOR UPDATE' in sql:
                                attempted.set()
                            return execute(sql, params, many, context)
                        with connection.execute_wrapper(signal_lock):
                            try:
                                if operation == 'task':
                                    add_task(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user,
                                             data={'title': 'Synthetic task', 'request_key': uuid4(), 'assigned_to': assignee})
                                else:
                                    save_vendor(dealership=self.dealer, actor=self.user, data={'name': 'Synthetic vendor'})
                            except (PermissionDenied, ValidationError):
                                return 'denied'
                            return 'saved'
                    finally:
                        connections.close_all()

                member = self.member if target == 'actor' else assignee_member
                user = self.user if target == 'actor' else assignee
                with ThreadPoolExecutor(max_workers=1) as pool:
                    with transaction.atomic():
                        Dealership.objects.select_for_update().get(pk=self.dealer.pk)
                        future = pool.submit(run)
                        self.assertTrue(attempted.wait(timeout=20))
                        if revocation == 'role':
                            Membership.objects.filter(pk=member.pk).update(role='viewer')
                        else:
                            get_user_model().objects.filter(pk=user.pk).update(is_active=False)
                    self.assertEqual(future.result(timeout=20), 'denied')
                self.assertEqual((ReconTask.objects.count(), VehicleVendor.objects.count(), VehicleVendorEvent.objects.count(), AuditEvent.objects.count()), (0, 0, 0, 0))
                Membership.objects.filter(pk=member.pk).update(role='staff')
                get_user_model().objects.filter(pk=user.pk).update(is_active=True)

    def test_actor_and_assignee_rechecked_after_membership_or_user_lock_wait(self):
        assignee = get_user_model().objects.create_user(username='locked-recon-assignee')
        assignee_member = Membership.objects.create(user=assignee, dealership=self.dealer, role='staff')
        for target, revocation in (('actor', 'role'), ('actor', 'inactive'),
                                   ('assignee', 'role'), ('assignee', 'inactive')):
            with self.subTest(target=target, revocation=revocation):
                user = self.user if target == 'actor' else assignee
                member = self.member if target == 'actor' else assignee_member
                attempted = Event()

                def run():
                    close_old_connections()
                    try:
                        def signal_lock(execute, sql, params, many, context):
                            if 'core_membership' in sql and 'FOR UPDATE' in sql and user.pk in params:
                                attempted.set()
                            return execute(sql, params, many, context)
                        with connection.execute_wrapper(signal_lock):
                            try:
                                add_task(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user,
                                         data={'title': 'Synthetic locked task', 'request_key': uuid4(), 'assigned_to': assignee})
                            except (PermissionDenied, ValidationError):
                                return 'denied'
                            return 'saved'
                    finally:
                        connections.close_all()

                with ThreadPoolExecutor(max_workers=1) as pool:
                    with transaction.atomic():
                        if revocation == 'role':
                            Membership.objects.select_for_update().get(pk=member.pk)
                        else:
                            get_user_model().objects.select_for_update().get(pk=user.pk)
                        future = pool.submit(run)
                        self.assertTrue(attempted.wait(timeout=20))
                        if revocation == 'role':
                            Membership.objects.filter(pk=member.pk).update(role='viewer')
                        else:
                            get_user_model().objects.filter(pk=user.pk).update(is_active=False)
                    self.assertEqual(future.result(timeout=20), 'denied')
                self.assertEqual((ReconTask.objects.count(), AuditEvent.objects.count()), (0, 0))
                Membership.objects.filter(pk=member.pk).update(role='staff')
                get_user_model().objects.filter(pk=user.pk).update(is_active=True)

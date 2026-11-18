# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import Client, TransactionTestCase
from django.urls import reverse

from core.models import AuditEvent, Dealership, Membership
from .models import Vehicle


@skipUnless(connection.vendor == 'postgresql', 'Row locking requires PostgreSQL')
class VehicleAuthorizationRaceTests(TransactionTestCase):
    def test_create_and_edit_recheck_identity_after_lock_wait(self):
        dealer = Dealership.objects.create(name='Synthetic vehicle race dealer')
        other = Dealership.objects.create(name='Synthetic other vehicle dealer')
        actor = get_user_model().objects.create_user('synthetic-vehicle-race')
        member = Membership.objects.create(user=actor, dealership=dealer, role='staff')
        vehicle = Vehicle.objects.create(dealership=dealer, stock_number='VEHICLE-RACE', year=2020, make='Synthetic', model='Original')
        client = Client()
        client.force_login(actor)
        data = {'stock_number': 'NEW-RACE', 'year': 2021, 'make': 'Synthetic', 'model': 'Changed',
                'vin': 'SYNTHETIC-VIN', 'status': 'recon', 'title_brand': 'unknown',
                'acquisition_cost': '0.00', 'recon_cost': '0.00'}
        for operation in ('create', 'edit'):
            for revoked in ('inactive', 'viewer', 'foreign', 'removed'):
                with self.subTest(operation=operation, revoked=revoked):
                    attempted = Event()
                    url = reverse('vehicle_create') if operation == 'create' else reverse('vehicle_edit', args=[vehicle.pk])
                    payload = data if operation == 'create' else data | {'stock_number': vehicle.stock_number, 'revision': 1}

                    def post():
                        close_old_connections()
                        try:
                            def signal_lock(execute, sql, params, many, context):
                                if 'core_membership' in sql and 'FOR UPDATE' in sql:
                                    attempted.set()
                                return execute(sql, params, many, context)
                            with connection.execute_wrapper(signal_lock):
                                return client.post(url, payload).status_code
                        finally:
                            close_old_connections()

                    with ThreadPoolExecutor(max_workers=1) as pool:
                        with transaction.atomic():
                            if revoked == 'inactive':
                                get_user_model().objects.select_for_update().get(pk=actor.pk)
                            else:
                                Membership.objects.select_for_update().get(pk=member.pk)
                            future = pool.submit(post)
                            self.assertTrue(attempted.wait(timeout=20))
                            if revoked == 'inactive':
                                get_user_model().objects.filter(pk=actor.pk).update(is_active=False)
                            elif revoked == 'viewer':
                                Membership.objects.filter(pk=member.pk).update(role='viewer')
                            elif revoked == 'foreign':
                                Membership.objects.filter(pk=member.pk).update(dealership=other)
                            else:
                                Membership.objects.filter(pk=member.pk).delete()
                        self.assertEqual(future.result(timeout=20), 403)
                    vehicle.refresh_from_db()
                    self.assertEqual((Vehicle.objects.count(), AuditEvent.objects.count(), vehicle.model, vehicle.revision), (1, 0, 'Original', 1))
                    get_user_model().objects.filter(pk=actor.pk).update(is_active=True)
                    member, _ = Membership.objects.update_or_create(user=actor, defaults={'dealership': dealer, 'role': 'staff'})

# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings

from core.models import Dealership, Membership
from customers.export import authorize_customer_export
from inventory.export import authorize_inventory_export


@skipUnless(connection.vendor == 'postgresql', 'Requires PostgreSQL row locking')
@override_settings(DEBUG=True, CUSTOMER_ACTIVITY_DEMO_ENABLED=True, RECON_DEMO_ENABLED=True)
class ExportLockOrderTests(TransactionTestCase):
    def test_dealership_lock_precedes_membership_for_standalone_exports(self):
        dealer = Dealership.objects.create(name='Synthetic lock-order dealer')
        user = get_user_model().objects.create_user('synthetic-export-owner')
        Membership.objects.create(user=user, dealership=dealer, role='owner')
        for authorize in (authorize_customer_export, authorize_inventory_export):
            started = Event()
            backend = []
            def export():
                close_old_connections()
                try:
                    with transaction.atomic():
                        with connection.cursor() as cursor:
                            cursor.execute('SELECT pg_backend_pid()')
                            backend.append(cursor.fetchone()[0])
                        started.set()
                        return authorize(dealership_id=dealer.pk, actor=user).pk
                finally:
                    close_old_connections()
            with self.subTest(export=authorize.__name__):
                with ThreadPoolExecutor(max_workers=1) as pool:
                    with transaction.atomic():
                        Dealership.objects.select_for_update().get(pk=dealer.pk)
                        result = pool.submit(export)
                        self.assertTrue(started.wait(10))
                        deadline = monotonic() + 10
                        while True:
                            with connection.cursor() as cursor:
                                cursor.execute('SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s', [backend[0]])
                                row = cursor.fetchone()
                            if row and row[0] == 'Lock':
                                break
                            if monotonic() >= deadline:
                                self.fail('Exporter did not block on the dealership lock')
                            sleep(0.02)
                        # Old ordering already holds membership while waiting.
                        Membership.objects.select_for_update(nowait=True).get(user=user)
                    self.assertIsNotNone(result.result(timeout=15))

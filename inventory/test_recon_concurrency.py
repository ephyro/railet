# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase, override_settings
from . import test_reconditioning as references
from .models import VehicleCostEntry, VehicleVendor
from .reconditioning import add_cost, reverse_cost


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

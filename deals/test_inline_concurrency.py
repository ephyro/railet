# SPDX-License-Identifier: MPL-2.0
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.db import connection,close_old_connections
from django.test import Client,TransactionTestCase,override_settings
from django.urls import reverse
from . import tests as fixtures
from .models import DraftDeal,DealEvent
from customers.models import Customer,CustomerEvent
from inventory.models import Vehicle
from core.models import AuditEvent

@skipUnless(connection.vendor=='postgresql','Inline creation concurrency requires PostgreSQL')
@override_settings(FL_TAX_ESTIMATES_ENABLED=True)
class InlineDeskingConcurrencyTests(TransactionTestCase):
    def test_one_vehicle_customer_and_deal_for_simultaneous_retries(self):
        fixtures.DraftWorkflowTests.setUp(self)
        data={**self.data,'vehicle_mode':'new','vehicle':'','newvehicle-stock_number':'RACE-DESK','newvehicle-year':'2020','newvehicle-make':'Synthetic','newvehicle-model':'Concurrent Desk',
              'customer_mode':'new','buyer':'','new-first_name':'Race New','new-last_name':'Synthetic','deal_type':'cash','tax_mode':'fl','tax_county':'Broward','tax_date':'2026-10-29'}
        ready=Barrier(2)
        def post():
            close_old_connections()
            try:
                client=Client();client.force_login(self.user);ready.wait(timeout=15)
                response=client.post(reverse('deal_create'),data);return response.status_code,response.get('Location')
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:post(),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0][0],302)
        deal=DraftDeal.objects.get();self.assertEqual(Vehicle.objects.filter(stock_number='RACE-DESK').count(),1)
        self.assertEqual(Customer.objects.filter(first_name='Race New').count(),1)
        self.assertEqual(AuditEvent.objects.filter(vehicle=deal.vehicle).count(),1)
        self.assertEqual(CustomerEvent.objects.filter(customer=deal.buyer).count(),1);self.assertEqual(DealEvent.objects.count(),1)

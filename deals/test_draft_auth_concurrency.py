# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import Client, TransactionTestCase
from django.urls import reverse

from core.models import Dealership, Membership
from customers.models import Customer
from inventory.models import Vehicle
from .models import DealEvent, DraftDeal, MONEY_FIELDS


@skipUnless(connection.vendor == 'postgresql', 'Row locking requires PostgreSQL')
class DraftAuthorizationRaceTests(TransactionTestCase):
    def test_create_edit_worksheet_and_retry_recheck_identity_after_wait(self):
        dealer = Dealership.objects.create(name='Synthetic draft race dealer')
        other = Dealership.objects.create(name='Synthetic foreign race dealer')
        actor = get_user_model().objects.create_user('synthetic-draft-race')
        member = Membership.objects.create(user=actor, dealership=dealer, role='staff')
        buyer = Customer.objects.create(dealership=dealer, first_name='Synthetic', last_name='Buyer')
        vehicle = Vehicle.objects.create(dealership=dealer, stock_number='RACE-1', year=2020, make='Synthetic', model='Car')
        client = Client()
        client.force_login(actor)
        data = {name: '0.00' for name in MONEY_FIELDS}
        data.update(vehicle=vehicle.pk, buyer=buyer.pk, customer_mode='existing', submission_key=str(uuid4()))
        self.assertEqual(client.post(reverse('deal_create'), data).status_code, 302)
        deal = DraftDeal.objects.get()
        worksheet = {name: str(getattr(deal, name)) for name in MONEY_FIELDS}
        worksheet.update(revision=deal.revision, notes='Unauthorized update', deal_type=deal.deal_type)
        requests = [(reverse('deal_create'), data),
                    (reverse('deal_create'), data | {'submission_key': str(uuid4())}),
                    (reverse('deal_edit', args=[deal.pk]), data | {'revision': deal.revision}),
                    (reverse('deal_detail', args=[deal.pk]), worksheet)]
        for url, payload in requests:
            for revoked in ('inactive', 'viewer', 'foreign', 'removed'):
                with self.subTest(url=url, revoked=revoked):
                    attempted = Event()

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
                    deal.refresh_from_db()
                    self.assertEqual((DraftDeal.objects.count(), DealEvent.objects.count(), deal.revision, deal.notes), (1, 1, 1, ''))
                    get_user_model().objects.filter(pk=actor.pk).update(is_active=True)
                    member, _ = Membership.objects.update_or_create(user=actor, defaults={'dealership': dealer, 'role': 'staff'})

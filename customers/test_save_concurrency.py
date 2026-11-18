# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection, transaction
from django.test import Client, TransactionTestCase
from django.urls import reverse

from core.models import Dealership, Membership
from deals.models import DealEvent, DraftDeal, MONEY_FIELDS
from inventory.models import Vehicle
from .forms import CustomerForm
from .models import Customer, CustomerEvent
from .services import save_customer


@skipUnless(connection.vendor == 'postgresql', 'Row locking requires PostgreSQL')
class CustomerSaveRaceTests(TransactionTestCase):
    def test_customer_and_inline_saves_recheck_identity_after_lock_wait(self):
        dealer = Dealership.objects.create(name='Synthetic customer race dealer')
        other = Dealership.objects.create(name='Synthetic foreign customer dealer')
        actor = get_user_model().objects.create_user('synthetic-customer-race')
        member = Membership.objects.create(user=actor, dealership=dealer, role='staff')
        customer = Customer.objects.create(dealership=dealer, first_name='Original', last_name='Synthetic')
        vehicle = Vehicle.objects.create(dealership=dealer, stock_number='CUSTOMER-RACE', year=2020, make='Synthetic', model='Car')
        client = Client()
        client.force_login(actor)
        data = {'first_name': 'Changed synthetic', 'last_name': 'Buyer', 'revision': 1}
        for operation in ('create', 'edit', 'direct_create', 'direct_edit', 'inline_deal'):
            for revoked in ('inactive', 'viewer', 'foreign', 'removed'):
                with self.subTest(operation=operation, revoked=revoked):
                    editing = operation == 'direct_edit'
                    form = CustomerForm(data, instance=Customer.objects.get(pk=customer.pk) if editing else Customer(dealership=dealer), dealership=dealer)
                    self.assertTrue(form.is_valid(), form.errors)
                    attempted = Event()

                    def save():
                        close_old_connections()
                        try:
                            def signal_lock(execute, sql, params, many, context):
                                if 'core_membership' in sql and 'FOR UPDATE' in sql:
                                    attempted.set()
                                return execute(sql, params, many, context)
                            with connection.execute_wrapper(signal_lock):
                                if operation.startswith('direct_'):
                                    try:
                                        save_customer(form, actor=actor, dealership=dealer)
                                    except PermissionDenied:
                                        return 403
                                    return 200
                                if operation == 'inline_deal':
                                    deal_data = {name: '0.00' for name in MONEY_FIELDS}
                                    deal_data.update(vehicle=vehicle.pk, customer_mode='new', buyer='',
                                                     **{'new-first_name': 'New synthetic', 'new-last_name': 'Buyer',
                                                        'submission_key': str(uuid4())})
                                    return client.post(reverse('deal_create'), deal_data).status_code
                                url = reverse('customer_create') if operation == 'create' else reverse('customer_edit', args=[customer.pk])
                                return client.post(url, data).status_code
                        finally:
                            close_old_connections()

                    with ThreadPoolExecutor(max_workers=1) as pool:
                        with transaction.atomic():
                            if revoked == 'inactive':
                                get_user_model().objects.select_for_update().get(pk=actor.pk)
                            else:
                                Membership.objects.select_for_update().get(pk=member.pk)
                            future = pool.submit(save)
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
                    customer.refresh_from_db()
                    self.assertEqual((Customer.objects.count(), CustomerEvent.objects.count(), DraftDeal.objects.count(), DealEvent.objects.count(), customer.first_name, customer.revision), (1, 0, 0, 0, 'Original', 1))
                    get_user_model().objects.filter(pk=actor.pk).update(is_active=True)
                    member, _ = Membership.objects.update_or_create(user=actor, defaults={'dealership': dealer, 'role': 'staff'})

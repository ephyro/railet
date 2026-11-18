# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from core.models import Dealership, Membership
from inventory.models import Vehicle


class FilteredExportFixture:
    def setUp(self):
        super().setUp()
        self.dealer = Dealership.objects.create(name='Synthetic filtered export dealer')
        self.other = Dealership.objects.create(name='Synthetic other export dealer')
        self.actor = get_user_model().objects.create_user('synthetic-filtered-export')
        self.member = Membership.objects.create(user=self.actor, dealership=self.dealer, role='staff')
        self.vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='EXPORT-1', year=2020, make='Synthetic', model='Car')
        self.routes = [
            (reverse('payment_register'), {'format': 'csv'}, ('get',)),
            (reverse('inventory_investment_report_export'), {}, ('get', 'head')),
            (reverse('recon_queue_export'), {}, ('get', 'head')),
            (reverse('vehicle_recon', args=[self.vehicle.pk]), {'export': 'costs'}, ('get', 'head')),
        ]
        self.client.force_login(self.actor)


@override_settings(DEMO_LEDGER_ENABLED=True, RECON_DEMO_ENABLED=True)
class FilteredExportAuthorizationTests(FilteredExportFixture, TestCase):
    def test_all_member_roles_keep_export_access(self):
        for role in ('owner', 'staff', 'viewer'):
            Membership.objects.filter(pk=self.member.pk).update(role=role)
            for url, params, methods in self.routes:
                for method in methods:
                    with self.subTest(role=role, url=url, method=method):
                        response = getattr(self.client, method)(url, params)
                        self.assertEqual(response.status_code, 200)
                        self.assertIn('no-store', response['Cache-Control'])

    def test_revocation_before_locked_check_denies_all_filtered_exports(self):
        select = Membership.objects.select_for_update
        for revoked in ('inactive', 'foreign', 'removed', 'invalid_role'):
            for url, params, methods in self.routes:
                for method in methods:
                    with self.subTest(revoked=revoked, url=url, method=method):
                        def revoke():
                            if revoked == 'inactive':
                                get_user_model().objects.filter(pk=self.actor.pk).update(is_active=False)
                            elif revoked == 'foreign':
                                Membership.objects.filter(pk=self.member.pk).update(dealership=self.other)
                            elif revoked == 'removed':
                                Membership.objects.filter(pk=self.member.pk).delete()
                            else:
                                Membership.objects.filter(pk=self.member.pk).update(role='invalid')
                            return select()
                        with patch('core.access.Membership.objects.select_for_update', side_effect=revoke):
                            response = getattr(self.client, method)(url, params)
                        self.assertEqual(response.status_code, 403)
                        self.assertIn('no-store', response['Cache-Control'])
                        self.assertNotIn(b'EXPORT-1', response.content)


@skipUnless(connection.vendor == 'postgresql', 'Row locking requires PostgreSQL')
@override_settings(DEMO_LEDGER_ENABLED=True, RECON_DEMO_ENABLED=True)
class FilteredExportRaceTests(FilteredExportFixture, TransactionTestCase):
    def test_identity_revocation_after_lock_wait_blocks_filtered_exports(self):
        for revoked in ('inactive', 'foreign', 'removed', 'invalid_role'):
            for url, params, methods in self.routes:
                for method in methods:
                    with self.subTest(revoked=revoked, url=url, method=method):
                        attempted = Event()

                        def download():
                            close_old_connections()
                            try:
                                def signal_lock(execute, sql, params, many, context):
                                    if 'core_membership' in sql and 'FOR UPDATE' in sql:
                                        attempted.set()
                                    return execute(sql, params, many, context)
                                with connection.execute_wrapper(signal_lock):
                                    response = getattr(self.client, method)(url, params)
                                    return response.status_code, response.content, response.get('Cache-Control', '')
                            finally:
                                close_old_connections()

                        with ThreadPoolExecutor(max_workers=1) as pool:
                            with transaction.atomic():
                                if revoked == 'inactive':
                                    get_user_model().objects.select_for_update().get(pk=self.actor.pk)
                                else:
                                    Membership.objects.select_for_update().get(pk=self.member.pk)
                                future = pool.submit(download)
                                self.assertTrue(attempted.wait(timeout=20))
                                if revoked == 'inactive':
                                    get_user_model().objects.filter(pk=self.actor.pk).update(is_active=False)
                                elif revoked == 'foreign':
                                    Membership.objects.filter(pk=self.member.pk).update(dealership=self.other)
                                elif revoked == 'removed':
                                    Membership.objects.filter(pk=self.member.pk).delete()
                                else:
                                    Membership.objects.filter(pk=self.member.pk).update(role='invalid')
                            status, body, cache = future.result(timeout=20)
                        self.assertEqual(status, 403)
                        self.assertEqual(body, b'')
                        self.assertIn('no-store', cache)
                        get_user_model().objects.filter(pk=self.actor.pk).update(is_active=True)
                        self.member, _ = Membership.objects.update_or_create(user=self.actor, defaults={'dealership': self.dealer, 'role': 'staff'})

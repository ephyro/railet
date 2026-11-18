# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Dealership, Membership
from customers.models import Customer
from deals.models import DraftDeal
from inventory.models import Vehicle
from .models import DemoDealPacket, DemoPacketExportEvent
from .packets import digest, source_digest


@skipUnless(connection.vendor == 'postgresql', 'Row locking requires PostgreSQL')
@override_settings(DEMO_PACKETS_ENABLED=True)
class PacketReadRaceTests(TransactionTestCase):
    def test_identity_revocation_blocks_artifact_and_bundle_preparation(self):
        dealer = Dealership.objects.create(name='Synthetic packet download dealer')
        other = Dealership.objects.create(name='Synthetic foreign download dealer')
        actor = get_user_model().objects.create_user('synthetic-packet-download')
        member = Membership.objects.create(user=actor, dealership=dealer, role='viewer')
        buyer = Customer.objects.create(dealership=dealer, first_name='Synthetic', last_name='Buyer')
        vehicle = Vehicle.objects.create(dealership=dealer, stock_number='DOWNLOAD-RACE', year=2020, make='Synthetic', model='Car')
        deal = DraftDeal.objects.create(dealership=dealer, vehicle=vehicle, buyer=buyer)
        snapshot = {'description': 'synthetic private data'}
        html = '<p>Synthetic private packet</p>'
        packet = DemoDealPacket.objects.create(deal=deal, created_by=actor, created_at=timezone.now(), creation_key=uuid4(),
                                               template_version='synthetic', snapshot=snapshot, source_sha256=source_digest(snapshot),
                                               html=html, artifact_sha256=digest(html))
        client = Client()
        client.force_login(actor)
        for route in ('demo_packet_artifact', 'demo_packet_export'):
            for method in ('get', 'head'):
                for revoked in ('inactive', 'foreign', 'removed', 'invalid_role'):
                    with self.subTest(route=route, method=method, revoked=revoked):
                        attempted = Event()
                        url = reverse(route, args=[deal.pk, packet.pk])

                        def download():
                            close_old_connections()
                            try:
                                def signal_lock(execute, sql, params, many, context):
                                    if 'core_membership' in sql and 'FOR UPDATE' in sql:
                                        attempted.set()
                                    return execute(sql, params, many, context)
                                with connection.execute_wrapper(signal_lock):
                                    response = getattr(client, method)(url)
                                    return response.status_code, response.content, response.get('Cache-Control', '')
                            finally:
                                close_old_connections()

                        with ThreadPoolExecutor(max_workers=1) as pool:
                            with transaction.atomic():
                                if revoked == 'inactive':
                                    get_user_model().objects.select_for_update().get(pk=actor.pk)
                                else:
                                    Membership.objects.select_for_update().get(pk=member.pk)
                                future = pool.submit(download)
                                self.assertTrue(attempted.wait(timeout=20))
                                if revoked == 'inactive':
                                    get_user_model().objects.filter(pk=actor.pk).update(is_active=False)
                                elif revoked == 'foreign':
                                    Membership.objects.filter(pk=member.pk).update(dealership=other)
                                elif revoked == 'removed':
                                    Membership.objects.filter(pk=member.pk).delete()
                                else:
                                    Membership.objects.filter(pk=member.pk).update(role='invalid')
                            status, body, cache = future.result(timeout=20)
                        self.assertEqual(status, 403)
                        self.assertNotIn(b'Synthetic private packet', body)
                        self.assertIn('no-store', cache)
                        self.assertEqual(DemoPacketExportEvent.objects.count(), 0)
                        get_user_model().objects.filter(pk=actor.pk).update(is_active=True)
                        member, _ = Membership.objects.update_or_create(user=actor, defaults={'dealership': dealer, 'role': 'viewer'})

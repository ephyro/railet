# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest import skipUnless
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings

from core.models import Dealership, Membership
from customers.models import Customer
from deals.models import DraftDeal
from inventory.models import Vehicle
from .models import DemoDealPacket
from .packets import create_packet, packet_source, source_digest


@skipUnless(connection.vendor == 'postgresql', 'Row locking requires PostgreSQL')
@override_settings(DEMO_PACKETS_ENABLED=True)
class PacketAuthorizationRaceTests(TransactionTestCase):
    def setUp(self):
        self.dealer = Dealership.objects.create(name='Synthetic packet race dealer')
        self.other = Dealership.objects.create(name='Synthetic foreign packet dealer')
        self.actor = get_user_model().objects.create_user('synthetic-packet-race')
        self.member = Membership.objects.create(user=self.actor, dealership=self.dealer, role='staff')
        buyer = Customer.objects.create(dealership=self.dealer, first_name='Synthetic', last_name='Buyer')
        vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='PACKET-RACE', year=2020, make='Synthetic', model='Car')
        deal = DraftDeal.objects.create(dealership=self.dealer, vehicle=vehicle, buyer=buyer)
        snapshot = packet_source(dealership_id=self.dealer.pk, deal_id=deal.pk)
        self.args = dict(dealership_id=self.dealer.pk, deal_id=deal.pk, actor=self.actor,
                         creation_key=uuid4(), expected_source=source_digest(snapshot))

    def test_identity_revocation_blocks_new_packets_and_retries(self):
        for already_saved in (False, True):
            if already_saved:
                packet, _ = create_packet(**self.args)
                frozen = (packet.html, packet.snapshot, packet.source_sha256, packet.artifact_sha256, packet.template_version)
            for revoked in ('inactive', 'viewer', 'foreign', 'removed'):
                with self.subTest(already_saved=already_saved, revoked=revoked):
                    attempted = Event()

                    def save():
                        close_old_connections()
                        try:
                            def signal_lock(execute, sql, params, many, context):
                                if 'core_membership' in sql and 'FOR UPDATE' in sql:
                                    attempted.set()
                                return execute(sql, params, many, context)
                            with connection.execute_wrapper(signal_lock):
                                try:
                                    create_packet(**self.args)
                                except PermissionDenied:
                                    return 'denied'
                                return 'saved'
                        finally:
                            close_old_connections()

                    with ThreadPoolExecutor(max_workers=1) as pool:
                        with transaction.atomic():
                            if revoked == 'inactive':
                                get_user_model().objects.select_for_update().get(pk=self.actor.pk)
                            else:
                                Membership.objects.select_for_update().get(pk=self.member.pk)
                            future = pool.submit(save)
                            self.assertTrue(attempted.wait(timeout=20))
                            if revoked == 'inactive':
                                get_user_model().objects.filter(pk=self.actor.pk).update(is_active=False)
                            elif revoked == 'viewer':
                                Membership.objects.filter(pk=self.member.pk).update(role='viewer')
                            elif revoked == 'foreign':
                                Membership.objects.filter(pk=self.member.pk).update(dealership=self.other)
                            else:
                                Membership.objects.filter(pk=self.member.pk).delete()
                        self.assertEqual(future.result(timeout=20), 'denied')
                    self.assertEqual(DemoDealPacket.objects.count(), int(already_saved))
                    if already_saved:
                        packet.refresh_from_db()
                        self.assertEqual((packet.html, packet.snapshot, packet.source_sha256, packet.artifact_sha256, packet.template_version), frozen)
                    get_user_model().objects.filter(pk=self.actor.pk).update(is_active=True)
                    self.member, _ = Membership.objects.update_or_create(user=self.actor, defaults={'dealership': self.dealer, 'role': 'staff'})

    def test_simultaneous_same_key_creates_one_frozen_packet(self):
        barrier = Barrier(2)

        def save():
            close_old_connections()
            try:
                barrier.wait(timeout=20)
                packet, created = create_packet(**self.args)
                return packet.pk, created
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result(timeout=30) for future in (pool.submit(save), pool.submit(save))]
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sorted(result[1] for result in results), [False, True])
        self.assertEqual(DemoDealPacket.objects.count(), 1)

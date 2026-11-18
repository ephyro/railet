# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from core.models import AuditEvent, Membership
from documents.models import DemoDealPacket
from inventory.inline import InlineVehicleForm, create_inline_vehicle
from inventory.models import Vehicle
from . import test_completion as reference
from .completion import complete
from .models import DealEvent, DemoDealCompletion


@skipUnless(connection.vendor == 'postgresql', 'Row locking requires PostgreSQL')
@override_settings(DEMO_COMPLETION_ENABLED=True, DEMO_PACKETS_ENABLED=True)
class AuxiliaryAuthorizationRaceTests(TransactionTestCase):
    def setUp(self):
        reference.CompletionTests.setUp(self)

    def source(self):
        return reference.CompletionTests.source(self)

    def test_lifecycle_completion_and_inline_recheck_identity_after_wait(self):
        args = reference.CompletionTests.args(self)
        member = Membership.objects.get(user=self.user)
        form = InlineVehicleForm({'stock_number': 'INLINE-RACE', 'year': '2020', 'make': 'Synthetic',
                                  'model': 'Car', 'status': 'recon', 'title_brand': 'unknown',
                                  'acquisition_cost': '0.00', 'recon_cost': '0.00'}, dealership=self.dealer)
        self.assertTrue(form.is_valid(), form.errors)
        for operation in ('lifecycle', 'complete', 'inline'):
            for revoked in ('inactive', 'viewer', 'foreign', 'removed'):
                with self.subTest(operation=operation, revoked=revoked):
                    attempted = Event()

                    def run():
                        close_old_connections()
                        try:
                            def signal_lock(execute, sql, params, many, context):
                                if 'core_membership' in sql and 'FOR UPDATE' in sql:
                                    attempted.set()
                                return execute(sql, params, many, context)
                            with connection.execute_wrapper(signal_lock):
                                try:
                                    if operation == 'lifecycle':
                                        return self.client.post(reverse('draft_lifecycle', args=[self.deal.pk]),
                                                                {'action': 'archive', 'revision': 1, 'reason': 'Synthetic'}).status_code
                                    if operation == 'complete':
                                        complete(**args)
                                    else:
                                        create_inline_vehicle(form, dealership=self.dealer, actor=self.user)
                                except PermissionDenied:
                                    return 403
                                return 200
                        finally:
                            close_old_connections()

                    with ThreadPoolExecutor(max_workers=1) as pool:
                        with transaction.atomic():
                            if revoked == 'inactive':
                                get_user_model().objects.select_for_update().get(pk=self.user.pk)
                            else:
                                Membership.objects.select_for_update().get(pk=member.pk)
                            future = pool.submit(run)
                            self.assertTrue(attempted.wait(timeout=20))
                            if revoked == 'inactive':
                                get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
                            elif revoked == 'viewer':
                                Membership.objects.filter(pk=member.pk).update(role='viewer')
                            elif revoked == 'foreign':
                                Membership.objects.filter(pk=member.pk).update(dealership=self.other)
                            else:
                                Membership.objects.filter(pk=member.pk).delete()
                        self.assertEqual(future.result(timeout=20), 403)
                    self.deal.refresh_from_db()
                    self.assertEqual((self.deal.revision, self.deal.archived_at), (1, None))
                    self.assertEqual((DemoDealCompletion.objects.count(), DemoDealPacket.objects.count(),
                                      DealEvent.objects.count(), AuditEvent.objects.count(),
                                      Vehicle.objects.filter(stock_number='INLINE-RACE').count()), (0, 0, 0, 0, 0))
                    get_user_model().objects.filter(pk=self.user.pk).update(is_active=True)
                    member, _ = Membership.objects.update_or_create(user=self.user, defaults={'dealership': self.dealer, 'role': 'staff'})

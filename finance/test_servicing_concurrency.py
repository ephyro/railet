# SPDX-License-Identifier: MPL-2.0
from unittest import skipUnless
from uuid import uuid4
from django.db import connection
from django.test import TransactionTestCase,override_settings
from . import test_servicing as references
from . import test_concurrency as concurrency
from .servicing_services import select_baseline
from .services import LedgerError
from .models import DemoServicingPlan

@skipUnless(connection.vendor=='postgresql','Servicing concurrency requires PostgreSQL')
@override_settings(DEMO_LEDGER_ENABLED=True,DEMO_SERVICING_ENABLED=True)
class ServicingConcurrencyTests(TransactionTestCase):
    def setUp(self):references.ServicingIntegrationTests.setUpTestData.__func__(type(self))
    def run_choice(self,key):
        return select_baseline(dealership_id=self.dealer.pk,book_id=self.book.pk,schedule_id=self.schedule.pk,actor=self.users['staff'],reason='Synthetic concurrent baseline',creation_key=key,expected_digest=self.schedule.result_sha256)
    def test_same_preview_selects_one_baseline(self):
        key=uuid4()
        def choose():
            obj,created=self.run_choice(key);return obj.pk,created
        results=concurrency.LedgerConcurrencyTests.race(self,[choose,choose])
        self.assertEqual(results[0][0],results[1][0])
        self.assertEqual(sum(created for _,created in results),1)
        self.assertEqual(DemoServicingPlan.objects.count(),1)
    def test_different_previews_cannot_replace_baseline(self):
        def choose():
            try:self.run_choice(uuid4());return 'selected'
            except LedgerError:return 'rejected'
        self.assertCountEqual(concurrency.LedgerConcurrencyTests.race(self,[choose,choose]),['selected','rejected'])
        self.assertEqual(DemoServicingPlan.objects.count(),1)

    def test_revocation_while_waiting_denies_schedule_and_baseline(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from django.contrib.auth import get_user_model
        from django.core.exceptions import PermissionDenied
        from django.db import close_old_connections, transaction
        from core.models import Dealership, Membership
        from .models import DemoSchedule
        from .schedule_services import save_illustration
        actor=self.users['staff']
        foreign=Dealership.objects.create(name='Synthetic foreign servicing dealer')
        initial_schedules=DemoSchedule.objects.count()
        initial_postings=self.book.postings.count()
        operations=[
            lambda: save_illustration(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=actor,
                inputs=self.schedule.inputs,expected_digest=self.schedule.result_sha256,creation_key=uuid4()),
            lambda: select_baseline(dealership_id=self.dealer.pk,book_id=self.book.pk,schedule_id=self.schedule.pk,
                actor=actor,reason='Synthetic baseline',creation_key=uuid4(),expected_digest=self.schedule.result_sha256),
        ]
        for operation in operations:
            for change in ('role','dealership','active'):
                with self.subTest(operation=operations.index(operation),change=change):
                    Membership.objects.filter(user=actor).update(role='staff',dealership=self.dealer)
                    get_user_model().objects.filter(pk=actor.pk).update(is_active=True)
                    started=Event()
                    def run():
                        from django.db import close_old_connections
                        close_old_connections()
                        try:
                            started.set()
                            try: operation()
                            except PermissionDenied: return 'denied'
                            return 'allowed'
                        finally: close_old_connections()
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        with transaction.atomic():
                            Dealership.objects.select_for_update().get(pk=self.dealer.pk)
                            future=pool.submit(run)
                            self.assertTrue(started.wait(10))
                            if change=='role': Membership.objects.filter(user=actor).update(role='viewer')
                            elif change=='dealership': Membership.objects.filter(user=actor).update(dealership=foreign)
                            else: get_user_model().objects.filter(pk=actor.pk).update(is_active=False)
                        self.assertEqual(future.result(timeout=15),'denied')
                    self.assertEqual(DemoSchedule.objects.count(),initial_schedules)
                    self.assertFalse(DemoServicingPlan.objects.exists())
                    self.assertEqual(self.book.postings.count(),initial_postings)

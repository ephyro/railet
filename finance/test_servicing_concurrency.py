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

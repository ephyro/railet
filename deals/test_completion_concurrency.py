# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.db import connection, connections, close_old_connections
from django.test import TransactionTestCase, override_settings
from . import test_completion as reference
from .completion import complete, CompletionChanged
from .models import DemoDealCompletion, DealEvent
from documents.models import DemoDealPacket


@skipUnless(connection.vendor=='postgresql','Concurrent completion requires PostgreSQL')
@override_settings(DEMO_COMPLETION_ENABLED=True,DEMO_PACKETS_ENABLED=True)
class CompletionConcurrencyTests(TransactionTestCase):
    def setUp(self):reference.CompletionTests.setUp(self)
    def source(self):return reference.CompletionTests.source(self)
    def args(self):return reference.CompletionTests.args(self)
    def race(self, functions):
        barrier=Barrier(len(functions))
        def run(function):
            close_old_connections()
            try:barrier.wait(timeout=10);return function()
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:return list(pool.map(run,functions))
    def test_same_confirmation_commits_one_completion_packet_and_audit(self):
        args=self.args()
        result=self.race([lambda:complete(**args).pk,lambda:complete(**args).pk])
        self.assertEqual(result[0],result[1])
        self.assertEqual(DemoDealCompletion.objects.count(),1);self.assertEqual(DemoDealPacket.objects.count(),1);self.assertEqual(DealEvent.objects.count(),1)
    def test_distinct_confirmations_cannot_complete_twice(self):
        first=self.args();second=self.args()
        def save(args):
            try:complete(**args);return 'saved'
            except CompletionChanged:return 'rejected'
        self.assertCountEqual(self.race([lambda:save(first),lambda:save(second)]),['saved','rejected'])
        self.assertEqual(DemoDealCompletion.objects.count(),1)

    def test_edit_and_completion_cannot_interleave_reviewed_figures(self):
        from django.db import transaction
        from django.core.exceptions import ValidationError
        from core.models import Dealership
        from .models import DraftDeal
        from .services import persist_draft
        args=self.args()
        def finish():
            try:complete(**args);return 'completed'
            except CompletionChanged:return 'completion_rejected'
        def edit():
            try:
                with transaction.atomic():
                    Dealership.objects.select_for_update().get(pk=self.dealer.pk)
                    deal=DraftDeal.objects.select_for_update().get(pk=self.deal.pk)
                    deal.sale_price=13000;deal.revision+=1
                    persist_draft(deal,actor=self.user)
                return 'edited'
            except ValidationError:return 'edit_rejected'
        result=self.race([finish,edit])
        self.assertIn(result,[['completed','edit_rejected'],['completion_rejected','edited']])
        self.deal.refresh_from_db()
        if result[0]=='completed':
            self.assertEqual(str(self.deal.sale_price),'12000.25')
            self.assertEqual(DemoDealCompletion.objects.get(deal=self.deal).packet.snapshot['worksheet']['sale_price'],'12000.25')
        else:
            self.assertEqual(self.deal.sale_price,13000)
            self.assertFalse(DemoDealCompletion.objects.exists())

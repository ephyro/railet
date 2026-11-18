# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, close_old_connections, transaction
from django.http import Http404
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from core.models import Membership
from finance import test_completed_handoff as fixture
from finance.models import DemoBook, DemoPosting
from .completion import (CompletionChanged, preview_void, void_completion,
                         preview_follow_on_draft, create_follow_on_draft)
from .models import DemoFollowOnDraft, DraftDeal, DealEvent


class FollowOnFixture:
    source = fixture.CompletedHandoffTests.source
    def setup_follow_on(self):
        fixture.CompletedHandoffTests.setUp(self)
        self.record = self.deal.demo_completion
        digest = preview_void(dealership_id=self.dealer.pk, deal_id=self.deal.pk, actor=self.user)[1]
        self.void = void_completion(dealership_id=self.dealer.pk, deal_id=self.deal.pk, actor=self.user,
            creation_key=uuid4(), expected_review=digest, reason='Synthetic void')
        self.args = dict(dealership_id=self.dealer.pk, deal_id=self.deal.pk, actor=self.user,
            creation_key=uuid4(), expected_review=self.preview()['review_sha256'], reason='Practice', confirmed=True)
    def preview(self):
        return preview_follow_on_draft(dealership_id=self.dealer.pk, deal_id=self.deal.pk, actor=self.user)


@override_settings(DEBUG=True, DEMO_LEDGER_ENABLED=True, DEMO_COMPLETION_ENABLED=True, DEMO_PACKETS_ENABLED=True)
class FollowOnTests(FollowOnFixture, TestCase):
    def setUp(self): self.setup_follow_on()

    def test_create_retry_history_export_and_original_preserved(self):
        old = (self.record.packet.html, self.record.packet.snapshot, self.record.review_sha256)
        result = create_follow_on_draft(**self.args)
        draft = result.draft
        self.assertNotEqual(draft.pk, self.deal.pk)
        self.assertEqual(draft.sale_price, self.deal.sale_price)
        self.assertEqual(draft.buyer_id, self.deal.buyer_id)
        self.assertFalse(draft.finance_proposals.exists()); self.assertFalse(draft.trades.exists())
        self.assertEqual(DealEvent.objects.get(deal=draft).snapshot['follow_on_provenance']['source_packet_id'], self.record.packet_id)
        self.record.refresh_from_db(); self.record.packet.refresh_from_db()
        self.assertEqual((self.record.packet.html, self.record.packet.snapshot, self.record.review_sha256), old)
        self.assertFalse(DemoBook.objects.exists()); self.assertFalse(DemoPosting.objects.exists())
        self.vehicle.status = 'sold'; self.vehicle.save()
        self.assertEqual(create_follow_on_draft(**self.args).pk, result.pk)
        with self.assertRaises(CompletionChanged): create_follow_on_draft(**(self.args | {'creation_key':uuid4()}))
        for operation in (lambda: DemoFollowOnDraft.objects.filter(pk=result.pk).update(reason='changed'),
                          lambda: DemoFollowOnDraft.objects.filter(pk=result.pk).delete()):
            with self.assertRaises(DatabaseError), transaction.atomic(): operation()
        Membership.objects.filter(user=self.user).update(role='owner')
        from .export import export_deals
        rows = export_deals(dealership_id=self.dealer.pk, actor=self.user)['follow_on_drafts']
        self.assertEqual([(row['draft_id'],row['void_rehearsal_id']) for row in rows], [(draft.pk,self.void.pk)])

    def test_unverified_figures_and_trade_adjustment_never_copy(self):
        from copy import deepcopy
        from decimal import Decimal
        from .completion import _follow_on_money
        from .models import MONEY_FIELDS
        snapshot = deepcopy(self.record.packet.snapshot)
        snapshot['worksheet']['trade_allowance'] = '100.00'
        code, amounts, tax, copied, notice = _follow_on_money(self.deal, snapshot, self.record.metadata)
        self.assertFalse(copied); self.assertTrue(all(value == 0 for value in amounts.values()))
        self.assertTrue(notice)
        snapshot = deepcopy(self.record.packet.snapshot)
        with patch.object(self.deal, 'trade_allowance', Decimal('100.00')):
            snapshot['worksheet']['trade_allowance'] = '100.00'
            code, amounts, tax, copied, notice = _follow_on_money(self.deal, snapshot, self.record.metadata)
        self.assertFalse(copied); self.assertIn('trade adjustment', notice)
        self.assertTrue(all(amounts[field] == 0 for field in MONEY_FIELDS))

    def test_production_disabled_even_if_demo_flags_are_overridden(self):
        with override_settings(DEBUG=False), self.assertRaises(Http404):
            self.preview()

    def test_stale_auth_scope_gate_and_rollback(self):
        with self.assertRaises(PermissionDenied): create_follow_on_draft(**(self.args | {'actor':self.users['viewer']}))
        with self.assertRaises(Http404): create_follow_on_draft(**(self.args | {'actor':self.users['foreign'], 'dealership_id':self.other.pk}))
        with self.assertRaises(CompletionChanged): create_follow_on_draft(**(self.args | {'confirmed':False}))
        with self.assertRaises(CompletionChanged): create_follow_on_draft(**(self.args | {'expected_review':'0'*64}))
        with patch('deals.completion.DealEvent.objects.create',side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError): create_follow_on_draft(**self.args)
        self.assertEqual(DraftDeal.objects.count(), 1); self.assertFalse(DemoFollowOnDraft.objects.exists())
        self.vehicle.revision += 1; self.vehicle.save()
        with self.assertRaises(CompletionChanged): create_follow_on_draft(**self.args)
        with override_settings(DEMO_COMPLETION_ENABLED=False), self.assertRaises(Http404): self.preview()

    def test_http_confirm_retry_tamper_and_csrf(self):
        url=reverse('deal_completion_follow_on', args=[self.deal.pk])
        self.client.force_login(self.users['viewer']); self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.users['foreign']); self.assertEqual(self.client.get(url).status_code,404)
        self.client.force_login(self.user)
        response=self.client.get(url); self.assertContains(response,'separate synthetic draft')
        token=response.context['form']['preview_token'].value()
        data={'preview_token':token,'reason':'Practice','confirmed':'on'}
        self.assertEqual(self.client.post(url,data | {'preview_token':token+'x'}).status_code,400)
        self.assertEqual(self.client.post(url,data).status_code,302)
        self.assertEqual(self.client.post(url,data).status_code,302)
        self.assertEqual(DemoFollowOnDraft.objects.count(),1)
        from django.test import Client
        strict=Client(enforce_csrf_checks=True); strict.force_login(self.user)
        self.assertEqual(strict.post(url,data).status_code,403)

    def test_stale_http_refresh_preserves_reason_and_requires_confirmation(self):
        url=reverse('deal_completion_follow_on',args=[self.deal.pk]); token=self.client.get(url).context['form']['preview_token'].value()
        self.buyer.revision+=1; self.buyer.save()
        response=self.client.post(url,{'preview_token':token,'reason':'Keep me','confirmed':'on'})
        self.assertEqual(response.status_code,409);self.assertContains(response,'Keep me',status_code=409)
        self.assertFalse(response.context['form']['confirmed'].value());self.assertFalse(DemoFollowOnDraft.objects.exists())


@override_settings(DEBUG=True, DEMO_LEDGER_ENABLED=True, DEMO_COMPLETION_ENABLED=True, DEMO_PACKETS_ENABLED=True)
class FollowOnRaceTests(FollowOnFixture, TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_identical_and_competing_requests_are_serialized(self):
        self.setup_follow_on(); barrier=Barrier(2)
        def submit(args):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try: return ('ok',create_follow_on_draft(**args).pk)
                except CompletionChanged: return ('conflict',None)
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            same=list(pool.map(submit,[self.args,self.args]))
        self.assertEqual(same[0],same[1]);self.assertEqual(same[0][0],'ok')
        self.assertEqual(DemoFollowOnDraft.objects.count(),1)
        barrier=Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            different=list(pool.map(submit,[self.args,self.args | {'creation_key':uuid4()}]))
        self.assertEqual(sorted(status for status,_ in different),['conflict','ok'])

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_distinct_first_requests_only_create_one(self):
        self.setup_follow_on(); barrier = Barrier(2)
        def submit(args):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try: return ('ok', create_follow_on_draft(**args).pk)
                except CompletionChanged: return ('conflict', None)
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(submit, [self.args, self.args | {'creation_key': uuid4()}]))
        self.assertEqual(sorted(status for status, _ in outcomes), ['conflict', 'ok'])
        self.assertEqual(DemoFollowOnDraft.objects.count(), 1)
        self.assertEqual(DraftDeal.objects.count(), 2)

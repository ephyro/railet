# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from . import tests as workflow_tests
from .models import DraftDeal, DraftFinanceProposal, DealEvent, MONEY_FIELDS


class FinanceProposalTests(TestCase):
    def setUp(self):
        workflow_tests.DraftWorkflowTests.setUp(self)
        self.client.post(reverse('deal_create'), self.data)
        self.deal = DraftDeal.objects.get()
        self.url = reverse('deal_detail', args=[self.deal.pk])

    def post(self, kind='bhph', **changes):
        self.deal.refresh_from_db()
        data = {name: str(getattr(self.deal, name)) for name in MONEY_FIELDS}
        data.update(revision=self.deal.revision, notes=self.deal.notes, deal_type=kind)
        data.update(changes)
        return self.client.post(self.url, data)

    def test_unknown_type_and_blank_terms_are_preserved_as_unknown(self):
        self.assertEqual(self.deal.deal_type, 'undecided')
        self.assertEqual(self.post(**{'bhph-included': '1'}).status_code, 302)
        self.assertFalse(DraftFinanceProposal.objects.exists())
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.deal_type, 'bhph')

    def test_separate_proposals_survive_cash_switch_and_omitted_forms(self):
        response = self.post(**{'bhph-included':'1', 'bhph-payment_count':'26', 'bhph-payment_frequency':'biweekly', 'bhph-annual_contract_rate':'0', 'outside-included':'1', 'outside-payment_count':'24', 'outside-payment_frequency':'semimonthly', 'outside-creditor_name':'Synthetic lender'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.post('cash').status_code, 302)
        self.assertEqual(self.post('outside').status_code, 302)
        bhph = DraftFinanceProposal.objects.get(kind='bhph')
        outside = DraftFinanceProposal.objects.get(kind='outside')
        self.assertEqual((bhph.payment_count, bhph.annual_contract_rate, bhph.first_payment_date), (26, Decimal('0'), None))
        self.assertEqual(outside.payment_frequency, 'semimonthly')
        self.assertIsNone(outside.annual_contract_rate)
        snapshot = DealEvent.objects.filter(deal=self.deal).first().snapshot
        self.assertEqual(snapshot['finance_proposals']['bhph']['annual_contract_rate'], '0.0000')
        self.assertEqual(snapshot['deal_type'], 'outside')

    def test_invalid_inactive_terms_block_all_changes_and_keep_entries(self):
        response = self.post('cash', **{'outside-included':'1','outside-payment_count':'0','outside-creditor_name':'Keep this entry','sale_price':'20000'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Keep this entry')
        self.assertTrue(response.context['proposal_errors'])
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.sale_price, Decimal('10000.10'))
        self.assertEqual(self.deal.deal_type, 'undecided')
        self.assertFalse(DraftFinanceProposal.objects.exists())

    def test_invalid_rate_date_frequency_and_type_do_not_save(self):
        for field, value in [('annual_contract_rate','-1'), ('annual_contract_rate','NaN'), ('payment_frequency','daily'), ('first_payment_date','2026-02-30'), ('payment_count','2.5')]:
            response = self.post(**{'bhph-included':'1',f'bhph-{field}':value})
            self.assertTrue(response.context['proposal_errors'], field)
        self.assertEqual(self.post('invented').status_code, 200)
        self.assertFalse(DraftFinanceProposal.objects.exists())
        self.assertEqual(DealEvent.objects.count(), 1)

    def test_revision_conflict_blocks_terms_and_audit_snapshot_is_immutable(self):
        first = DealEvent.objects.get().snapshot
        self.assertEqual(self.post(**{'bhph-included':'1','bhph-payment_count':'12'}).status_code,302)
        stale = self.post(**{'revision':1,'bhph-included':'1','bhph-payment_count':'99'})
        self.assertEqual(stale.status_code,409)
        self.assertEqual(DraftFinanceProposal.objects.get().payment_count,12)
        self.assertEqual(DealEvent.objects.order_by('pk').first().snapshot,first)

    def test_noop_and_audit_failure_do_not_create_partial_changes(self):
        self.post(**{'bhph-included':'1','bhph-payment_count':'12'})
        self.post(**{'bhph-included':'1','bhph-payment_count':'12'})
        self.assertEqual(DealEvent.objects.count(),2)
        with patch('deals.services.DealEvent.objects.create',side_effect=RuntimeError('unavailable')):
            with self.assertRaises(RuntimeError):
                self.post('cash', **{'bhph-included':'1','bhph-payment_count':'20'})
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.deal_type,'bhph')
        self.assertEqual(DraftFinanceProposal.objects.get().payment_count,12)

    def test_viewer_cannot_write_and_submitted_ownership_fields_are_ignored(self):
        self.post(**{'bhph-included':'1','bhph-payment_count':'10','bhph-kind':'outside','bhph-deal':'99999'})
        proposal = DraftFinanceProposal.objects.get()
        self.assertEqual((proposal.kind,proposal.deal_id),('bhph',self.deal.pk))
        self.member.role='viewer'; self.member.save()
        self.assertEqual(self.post().status_code,403)
        self.assertEqual(self.client.get(self.url).status_code,200)

    def test_interest_methods_are_explicit_separate_and_snapshotted(self):
        self.assertEqual(self.post(**{'bhph-included':'1', 'bhph-interest_method':'precomputed', 'outside-included':'1', 'outside-interest_method':'simple'}).status_code,302)
        self.assertEqual(DraftFinanceProposal.objects.get(kind='bhph').interest_method,'precomputed')
        self.assertEqual(DraftFinanceProposal.objects.get(kind='outside').interest_method,'simple')
        snapshot = DealEvent.objects.filter(deal=self.deal).first().snapshot
        self.assertEqual(snapshot['finance_proposals']['bhph']['interest_method'],'precomputed')
        self.assertEqual(snapshot['finance_proposals']['outside']['interest_method'],'simple')

    def test_omitted_method_preserves_selection_but_explicit_blank_clears(self):
        self.post(**{'bhph-included':'1','bhph-interest_method':'precomputed'})
        self.post(**{'bhph-included':'1','bhph-payment_count':'12'})
        self.assertEqual(DraftFinanceProposal.objects.get().interest_method,'precomputed')
        self.post(**{'bhph-included':'1','bhph-interest_method':''})
        self.assertEqual(DraftFinanceProposal.objects.get().interest_method,'')

    def test_invalid_method_blocks_save_and_preserves_work(self):
        response = self.post(**{'bhph-included':'1','bhph-interest_method':'invented','bhph-creditor_name':'Keep my entry'})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.context['proposal_errors'])
        self.assertContains(response,'Keep my entry')
        self.assertFalse(DraftFinanceProposal.objects.exists())

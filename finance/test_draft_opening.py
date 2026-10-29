# SPDX-License-Identifier: MPL-2.0
from datetime import date
from uuid import uuid4
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import Membership
from .models import DemoBook, DemoPosting, DemoAccountContext
from . import test_accounts as account_fixtures


@override_settings(DEMO_LEDGER_ENABLED=True)
class DraftAccountOpeningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        account_fixtures.AccountWorkspaceTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.users['staff'])
        self.url=reverse('draft_demo_account',args=[self.deal.pk])
        self.data={'amount':'1200.25','effective_on':'2026-01-01','reference':'Invented opening reference','request_key':str(uuid4()),'synthetic_confirmed':'on'}

    def preview(self):
        response=self.client.post(self.url,self.data)
        self.assertEqual(response.status_code,200)
        return response.context['token']

    def save(self,token,**extra):return self.client.post(self.url,{'preview_token':token,'action':'open',**extra})

    def test_opening_is_explicit_and_preview_creates_nothing(self):
        response=self.client.get(self.url)
        self.assertIsNone(response.context['form']['amount'].value())
        self.assertNotIn('customer',response.context['form'].fields)
        before=(DemoBook.objects.count(),DemoPosting.objects.count())
        preview=self.client.post(self.url,self.data)
        self.assertContains(preview,'Nothing has been created')
        self.assertEqual((DemoBook.objects.count(),DemoPosting.objects.count()),before)
        self.assertFalse(DemoAccountContext.objects.exists())

    def test_opening_reuses_parties_and_preserves_terms_without_selling_vehicle(self):
        self.data.update(customer='99999',deal='99999',vehicle='99999')
        response=self.save(self.preview())
        self.assertEqual(response.status_code,302)
        saved=DemoAccountContext.objects.get()
        self.assertEqual(saved.book.customer_id,self.customer.pk)
        self.assertEqual(saved.snapshot['vehicle_id'],self.vehicle.pk)
        self.assertEqual(saved.snapshot['interest_method'],'Precomputed')
        self.assertEqual(saved.book.postings.get(kind='opening').amount_cents,120025)
        self.assertEqual(saved.book.source_reference,'Invented opening reference')
        self.assertFalse(saved.book.postings.filter(kind='receipt').exists())
        self.vehicle.refresh_from_db();self.deal.refresh_from_db()
        self.assertNotEqual(self.vehicle.status,'sold')
        self.assertEqual(self.deal.revision,1)
        self.assertContains(self.client.get(reverse('deal_detail',args=[self.deal.pk])),response.url)
        self.assertEqual(self.client.get(self.url).url,response.url)

    def test_same_preview_retry_returns_original_after_source_changes(self):
        token=self.preview();first=self.save(token)
        self.proposal.interest_method='simple';self.proposal.save()
        self.deal.archived_at=timezone.now();self.deal.save()
        self.assertEqual(self.save(token).url,first.url)
        self.assertEqual(DemoAccountContext.objects.count(),1)
        self.assertEqual(DemoAccountContext.objects.get().snapshot['interest_method'],'Precomputed')

    def test_new_preview_cannot_create_a_second_account(self):
        first=self.preview();self.data['request_key']=str(uuid4());other=self.preview()
        self.assertEqual(self.save(first).status_code,302)
        response=self.save(other)
        self.assertEqual(response.status_code,409)
        self.assertContains(response,'already has a demo account',status_code=409)
        self.assertEqual(DemoAccountContext.objects.count(),1)

    def test_stale_proposed_terms_and_archived_draft_require_review(self):
        token=self.preview();self.proposal.interest_method='simple';self.proposal.save()
        response=self.save(token)
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.context['form']['amount'].value(),'1200.25')
        self.assertFalse(DemoAccountContext.objects.exists())
        token=self.preview();self.deal.archived_at=timezone.now();self.deal.save()
        self.assertEqual(self.save(token).status_code,409)

    def test_form_errors_preserve_work_and_edit_creates_nothing(self):
        self.data['amount']='1.001'
        response=self.client.post(self.url,self.data)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(response.context['form']['reference'].value(),self.data['reference'])
        self.data['amount']='1200.25';token=self.preview()
        response=self.save(token,action='edit')
        self.assertEqual(response.context['form']['amount'].value(),'1200.25')
        self.assertFalse(DemoAccountContext.objects.exists())

    def test_failure_rolls_back_opening_and_context_together(self):
        token=self.preview();before=DemoBook.objects.count()
        with patch('finance.account_services.link_draft',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):self.save(token)
        self.assertEqual(DemoBook.objects.count(),before)
        self.assertEqual(DemoPosting.objects.count(),1)
        self.assertFalse(DemoAccountContext.objects.exists())

    def test_request_cannot_reuse_key_with_different_facts(self):
        token=self.preview();self.save(token)
        self.data['amount']='1200.26';other=self.preview()
        self.assertEqual(self.save(other).status_code,409)
        self.assertEqual(DemoAccountContext.objects.count(),1)

    def test_permissions_scope_gate_and_tampered_preview(self):
        token=self.preview()
        self.assertEqual(self.save(token+'bad').status_code,400)
        other_user=get_user_model().objects.create_user('other-opening-staff')
        Membership.objects.create(user=other_user,dealership=self.dealer,role='staff')
        self.client.force_login(other_user)
        self.assertEqual(self.save(token).status_code,403)
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.client.get(self.url).status_code,403)
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.client.force_login(self.users['staff'])
        with override_settings(DEMO_LEDGER_ENABLED=False):self.assertEqual(self.save(token).status_code,403)

    def test_non_bhph_draft_is_not_eligible(self):
        self.deal.deal_type='cash';self.deal.save()
        self.assertEqual(self.client.get(self.url).status_code,409)
        self.assertFalse(DemoAccountContext.objects.exists())

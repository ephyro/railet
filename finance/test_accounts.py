# SPDX-License-Identifier: MPL-2.0
from datetime import date
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import Dealership, Membership
from customers.models import Customer
from inventory.models import Vehicle
from deals.models import DraftDeal, DraftFinanceProposal
from .models import DemoAccountContext, DemoPosting
from .services import open_book, record_receipt, reverse_receipt


@override_settings(DEMO_LEDGER_ENABLED=True)
class AccountWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer=Dealership.objects.create(name='Synthetic account workspace')
        cls.other=Dealership.objects.create(name='Other workspace')
        cls.users={}
        for name,role,dealer in [('staff','staff',cls.dealer),('viewer','viewer',cls.dealer),('foreign','owner',cls.other)]:
            user=get_user_model().objects.create_user('account-'+name)
            Membership.objects.create(user=user,dealership=dealer,role=role)
            cls.users[name]=user
        cls.customer=Customer.objects.create(dealership=cls.dealer,first_name='Riley',last_name='Demo')
        cls.vehicle=Vehicle.objects.create(dealership=cls.dealer,stock_number='DEMO-ACCOUNT',year=2020,make='Synthetic',model='Sedan')
        cls.deal=DraftDeal.objects.create(dealership=cls.dealer,buyer=cls.customer,vehicle=cls.vehicle,deal_type='bhph')
        cls.proposal=DraftFinanceProposal.objects.create(deal=cls.deal,kind='bhph',interest_method='precomputed',payment_frequency='monthly',payment_count=12)
        cls.book,_=open_book(dealership_id=cls.dealer.pk,customer_id=cls.customer.pk,actor=cls.users['staff'],label='Demo BHPH workspace',source_reference='Invented opening',opening_on=date(2026,1,1),opening_amount='1000.00',request_key=uuid4())

    def setUp(self):
        self.client.force_login(self.users['staff'])
        self.url=reverse('bhph_account',args=[self.book.pk])
        self.link=reverse('bhph_account_link',args=[self.book.pk])

    def preview(self):
        response=self.client.post(self.link,{'deal':self.deal.pk})
        self.assertEqual(response.status_code,200)
        return response.context['token']

    def save(self,token):return self.client.post(self.link,{'preview_token':token})

    def receipt(self):
        posting,_=record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.users['staff'],amount='125.50',effective_on=date(2026,2,1),reason='Invented cash receipt',request_key=uuid4())
        return posting

    def test_workspace_has_clear_empty_states_and_never_infers_a_draft(self):
        response=self.client.get(self.url)
        self.assertContains(response,'No vehicle linked.')
        self.assertContains(response,'Record payment')
        self.assertContains(response,'No payments recorded.')
        self.assertContains(response,'$1,000.00')
        self.assertFalse(DemoAccountContext.objects.exists())
        self.assertIn('no-store',response['Cache-Control'])
        self.assertEqual(self.client.post(self.url).status_code,405)

    def test_link_preview_retry_and_frozen_terms_leave_postings_unchanged(self):
        token=self.preview()
        self.assertFalse(DemoAccountContext.objects.exists())
        self.assertEqual(self.save(token).status_code,302)
        self.proposal.interest_method='simple';self.proposal.save()
        self.vehicle.model='Changed later';self.vehicle.save()
        self.assertEqual(self.save(token).status_code,302)
        self.assertEqual(DemoAccountContext.objects.count(),1)
        response=self.client.get(self.url)
        self.assertContains(response,'Precomputed')
        self.assertContains(response,'Synthetic Sedan')
        self.assertNotContains(response,'Changed later')
        self.assertEqual(DemoPosting.objects.count(),1)

    def test_changed_preview_requires_review(self):
        token=self.preview()
        self.proposal.interest_method='simple';self.proposal.save()
        self.assertEqual(self.save(token).status_code,409)
        self.assertFalse(DemoAccountContext.objects.exists())

    def test_wrong_customer_cash_archived_and_foreign_drafts_cannot_link(self):
        other_person=Customer.objects.create(dealership=self.dealer,first_name='Other')
        for changes in ({'buyer':other_person},{'deal_type':'cash'},{'archived_at':timezone.now()},{'dealership':self.other}):
            draft=DraftDeal.objects.create(dealership=self.dealer,buyer=self.customer,vehicle=self.vehicle,deal_type='bhph')
            for name,value in changes.items():setattr(draft,name,value)
            draft.save()
            response=self.client.post(self.link,{'deal':draft.pk})
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.context['form'].errors)
            self.assertNotIn('token',response.context)
        self.assertFalse(DemoAccountContext.objects.exists())

    def test_viewer_reads_but_cannot_link_or_record_and_foreign_cannot_read(self):
        posting=self.receipt();receipt_url=reverse('bhph_account_receipt',args=[self.book.pk,posting.pk])
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.assertEqual(self.client.get(receipt_url).status_code,200)
        self.assertEqual(self.client.get(self.link).status_code,403)
        self.assertEqual(self.client.get(reverse('ledger_demo_receipt',args=[self.book.pk])).status_code,403)
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.assertEqual(self.client.get(receipt_url).status_code,404)

    def test_tampered_and_wrong_actor_tokens_cannot_link(self):
        token=self.preview()
        self.assertEqual(self.save(token+'bad').status_code,200)
        self.assertFalse(DemoAccountContext.objects.exists())
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.save(token).status_code,404)

    def test_receipt_and_linked_correction_keep_original_amount_and_principal(self):
        posting=self.receipt();url=reverse('bhph_account_receipt',args=[self.book.pk,posting.pk])
        self.assertContains(self.client.get(url),'Unapplied')
        reverse_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,posting_id=posting.pk,actor=self.users['staff'],effective_on=date(2026,2,2),reason='Synthetic full correction',request_key=uuid4())
        response=self.client.get(url)
        self.assertContains(response,'Reversed in full')
        self.assertContains(response,'$125.50')
        self.assertContains(response,'Synthetic full correction')
        workspace=self.client.get(self.url)
        self.assertEqual(workspace.context['principal'],'$1,000.00')
        self.assertEqual(workspace.context['unapplied'],'$0.00')
        opening=self.book.postings.get(kind='opening')
        self.assertEqual(self.client.get(reverse('bhph_account_receipt',args=[self.book.pk,opening.pk])).status_code,404)

    def test_saved_context_database_rejects_updates_and_deletes(self):
        self.save(self.preview())
        for operation in ('update','delete'):
            with self.assertRaises(DatabaseError),transaction.atomic():
                query=DemoAccountContext.objects.all()
                query.update(snapshot={}) if operation=='update' else query.delete()

    def test_customer_navigation_and_production_gate(self):
        response=self.client.get(reverse('customer_detail',args=[self.customer.pk]))
        self.assertContains(response,self.url)
        with override_settings(DEMO_LEDGER_ENABLED=False):
            self.assertEqual(self.client.get(self.url).status_code,403)
            self.assertEqual(self.client.get(self.link).status_code,403)
            self.assertNotContains(self.client.get(reverse('customer_detail',args=[self.customer.pk])),'BHPH demo accounts')

    def test_payment_preview_posts_once_and_returns_to_its_receipt(self):
        data={'amount':'125.50','effective_on':'2026-02-01','reference':'Invented counter payment','request_key':str(uuid4()),'synthetic_confirmed':'on'}
        preview=self.client.post(reverse('ledger_demo_receipt',args=[self.book.pk]),data)
        self.assertEqual(DemoPosting.objects.count(),1)
        response=self.client.post(reverse('ledger_demo_confirm'),{'preview_token':preview.context['token'],'action':'post'})
        retry=self.client.post(reverse('ledger_demo_confirm'),{'preview_token':preview.context['token'],'action':'post'})
        self.assertEqual(response.url,retry.url)
        posting=self.book.postings.get(kind='receipt')
        self.assertEqual(response.url,reverse('bhph_account_receipt',args=[self.book.pk,posting.pk]))
        self.assertEqual(self.book.postings.count(),2)

    def test_receipts_cannot_be_read_through_another_book(self):
        posting=self.receipt()
        other_book,_=open_book(dealership_id=self.dealer.pk,customer_id=self.customer.pk,actor=self.users['staff'],label='Other invented account',source_reference='Synthetic',opening_on=date(2026,1,1),opening_amount='500',request_key=uuid4())
        self.assertEqual(self.client.get(reverse('bhph_account_receipt',args=[other_book.pk,posting.pk])).status_code,404)

    def test_payment_history_is_paginated(self):
        for number in range(21):
            record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.users['staff'],amount='1',effective_on=date(2026,2,1),reason=f'Synthetic receipt {number}',request_key=uuid4())
        first=self.client.get(self.url)
        self.assertEqual(len(first.context['rows']),20)
        second=self.client.get(self.url+'?page=2')
        self.assertEqual(len(second.context['rows']),1)
        self.assertEqual(second.context['unapplied'],'$21.00')

    def test_overview_does_not_present_unapplied_funds_as_amount_due_or_lateness(self):
        self.receipt()
        response = self.client.get(self.url)
        overview = response.content.decode().split('aria-label="Payment overview">', 1)[1].split('</section>', 1)[0]
        self.assertIn('Amount due', overview)
        self.assertIn('Not calculated', overview)
        self.assertIn('Late status', overview)
        self.assertIn('Not assessed', overview)
        self.assertNotIn('$', overview)
        self.assertContains(response, '$125.50')
        self.assertContains(response, '$1,000.00')

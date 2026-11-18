# SPDX-License-Identifier: MPL-2.0
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import Dealership, Membership
from customers.models import Customer
from inventory.models import Vehicle
from documents.models import DemoDealPacket, DealFile
from finance.models import DemoBook
from .models import DraftDeal, DraftFinanceProposal, DraftTradeIn, DealEvent, DemoDealCompletion
from .completion import preview, complete, verified_snapshot, CompletionChanged
from .services import persist_draft


@override_settings(DEMO_COMPLETION_ENABLED=True,DEMO_PACKETS_ENABLED=True)
class CompletionTests(TestCase):
    def setUp(self):
        self.dealer=Dealership.objects.create(name='Synthetic completion dealer')
        self.other=Dealership.objects.create(name='Other synthetic completion dealer')
        self.users={}
        for name,role,dealer in [('staff','staff',self.dealer),('viewer','viewer',self.dealer),('foreign','owner',self.other)]:
            user=get_user_model().objects.create_user('completion-'+name)
            Membership.objects.create(user=user,dealership=dealer,role=role);self.users[name]=user
        self.user=self.users['staff']
        self.vehicle=Vehicle.objects.create(dealership=self.dealer,stock_number='COMPLETE-1',year=2021,make='Synthetic',model='Review Sedan')
        self.buyer=Customer.objects.create(dealership=self.dealer,first_name='Practice',last_name='Buyer')
        self.deal=DraftDeal.objects.create(dealership=self.dealer,vehicle=self.vehicle,buyer=self.buyer,deal_type='cash',sale_price=Decimal('12000.25'),tax=Decimal('700.00'),dealer_fee=Decimal('99.75'),down_payment=Decimal('1000.00'))
        self.client.force_login(self.user)

    def source(self):return preview(dealership_id=self.dealer.pk,deal_id=self.deal.pk)
    def args(self,**changes):
        return dict(dealership_id=self.dealer.pk,deal_id=self.deal.pk,actor=self.user,creation_key=uuid4(),expected_review=self.source()['review_sha256'],review_notes='Invented workflow; title and mileage reminders retained for review.',reviewed=True,demo_confirmed=True,**changes)
    def finish(self):return complete(**self.args())

    def test_inactive_actor_cannot_complete_or_retry(self):
        args = self.args()
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            complete(**args)
        self.assertEqual((DemoDealCompletion.objects.count(), DemoDealPacket.objects.count(), DealEvent.objects.count()), (0, 0, 0))
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=True)
        complete(**args)
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            complete(**args)
        self.assertEqual((DemoDealCompletion.objects.count(), DemoDealPacket.objects.count(), DealEvent.objects.count()), (1, 1, 1))
    def token(self):
        response=self.client.get(reverse('deal_completion_prepare',args=[self.deal.pk]))
        return response.context['form']['preview_token'].value()
    def post(self,token,**changes):
        return self.client.post(reverse('deal_completion_prepare',args=[self.deal.pk]),dict(preview_token=token,reviewed='on',demo_confirmed='on',review_notes='Practice reminders remain recorded.',**changes))

    def test_completion_snapshot_reference_and_no_financial_side_effect(self):
        record=self.finish();snapshot=verified_snapshot(record)
        self.assertEqual(snapshot['worksheet_rows'][-1][1],'$11,800.00')
        self.assertEqual(record.source_revision,1)
        self.vehicle.refresh_from_db();self.assertEqual(self.vehicle.status,'acquired')
        self.assertEqual(DemoBook.objects.count(),0)
        self.assertEqual(DealEvent.objects.get(deal=self.deal).snapshot['action'],'completion_rehearsed')
        self.assertEqual(DemoDealPacket.objects.count(),1)
        self.assertTrue(snapshot['reminders'])

    def test_same_confirmation_retries_after_profile_change_return_one_record(self):
        args=self.args();record=complete(**args)
        self.buyer.first_name='Changed current profile';self.buyer.save()
        self.assertEqual(complete(**args).pk,record.pk)
        self.assertEqual(DemoDealCompletion.objects.count(),1)
        self.assertEqual(DemoDealPacket.objects.count(),1)
        self.assertEqual(DealEvent.objects.count(),1)
        with self.assertRaises(CompletionChanged):complete(**(args|{'creation_key':uuid4()}))

    def test_saved_snapshot_and_list_ignore_current_profile_and_vehicle_edits(self):
        record=self.finish();source=record.packet.snapshot
        self.buyer.first_name='New current name';self.buyer.save()
        self.vehicle.model='Changed current model';self.vehicle.save()
        record.refresh_from_db();self.assertEqual(verified_snapshot(record),source)
        response=self.client.get(reverse('deal_completion',args=[self.deal.pk]))
        self.assertContains(response,'Practice Buyer');self.assertContains(response,'Review Sedan')
        self.assertNotContains(response,'New current name');self.assertNotContains(response,'Changed current model')
        response=self.client.get(reverse('deals'),{'scope':'completed'})
        self.assertContains(response,'Practice Buyer');self.assertNotContains(response,'New current name')
        for query in ['Practice Buyer','Review Sedan','COMPLETE-1']:
            searched=self.client.get(reverse('deals'),{'scope':'completed','q':query})
            self.assertEqual(searched.context['page_obj'].paginator.count,1)

    def test_blockers_and_required_acknowledgements(self):
        for changes in [{'deal_type':'undecided'},{'sale_price':0},{'down_payment':Decimal('20000')},{'archived_at':timezone.now()}]:
            original={key:getattr(self.deal,key) for key in changes}
            for key,value in changes.items():setattr(self.deal,key,value)
            self.deal.save()
            self.assertTrue(self.source()['blockers'])
            with self.assertRaises(CompletionChanged):self.finish()
            for key,value in original.items():setattr(self.deal,key,value)
            self.deal.save()
        for changes in [{'reviewed':False},{'demo_confirmed':False},{'review_notes':''}]:
            with self.assertRaises(CompletionChanged):complete(**(self.args()|changes))
        self.assertFalse(DemoDealCompletion.objects.exists())

    def test_selected_financing_terms_required_and_zero_rate_recorded(self):
        self.deal.deal_type='bhph';self.deal.save()
        self.assertTrue(self.source()['blockers'])
        proposal=DraftFinanceProposal.objects.create(deal=self.deal,kind='bhph',interest_method='simple',creditor_name='Practice Creditor',payment_frequency='monthly',payment_count=24,annual_contract_rate=Decimal('0'),first_payment_date=date(2026,12,1))
        self.assertFalse(self.source()['blockers'])
        proposal.creditor_name='';proposal.first_payment_date=None;proposal.save()
        blocker=self.source()['blockers'][0]
        self.assertIn('creditor or lender',blocker['title']);self.assertIn('first payment date',blocker['title'])
        self.assertNotIn('number of payments',blocker['title'])
        proposal.creditor_name='Practice Creditor';proposal.first_payment_date=date(2026,12,1);proposal.save()
        proposal.interest_method='precomputed';proposal.save()
        self.assertTrue(self.source()['blockers'])
        proposal.illustration_finance_charge=Decimal('0');proposal.save()
        self.assertFalse(self.source()['blockers'])
        self.finish();self.assertFalse(DemoBook.objects.exists())

    def test_source_changes_invalidate_preview_including_files_and_revisions(self):
        old=self.args()
        self.buyer.phone='5550100100';self.buyer.revision+=1;self.buyer.save()
        with self.assertRaises(CompletionChanged):complete(**old)
        old=self.args()
        DealFile.objects.create(deal=self.deal,title='Synthetic new file',blob='not-a-real-file.pdf',sha256='a'*64,byte_size=12,created_by=self.user)
        with self.assertRaises(CompletionChanged):complete(**old)
        self.assertFalse(DemoDealPacket.objects.exists())

    def test_file_manifest_retained_without_claiming_document_verification(self):
        file=DealFile.objects.create(deal=self.deal,title='Practice supporting file',blob='synthetic-reference.pdf',sha256='b'*64,byte_size=32,created_by=self.user)
        record=self.finish()
        self.assertEqual(record.metadata['files'][0]['sha256'],'b'*64)
        file.archived_at=timezone.now();file.save()
        self.assertEqual(verified_snapshot(record)['buyer']['name'],'Practice Buyer')
        response=self.client.get(reverse('deal_completion',args=[self.deal.pk]))
        self.assertContains(response,'Practice supporting file')
        self.assertContains(response,'not a verification')

    def test_scope_roles_csrf_and_disabled_gate(self):
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(reverse('deal_completion_prepare',args=[self.deal.pk])).status_code,404)
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.client.get(reverse('deal_completion_prepare',args=[self.deal.pk])).status_code,403)
        with self.assertRaises(PermissionDenied):complete(**(self.args()|{'actor':self.users['viewer']}))
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post(reverse('deal_completion_prepare',args=[self.deal.pk]),{}).status_code,403)
        self.client.force_login(self.user)
        with override_settings(DEMO_COMPLETION_ENABLED=False):
            self.assertEqual(self.client.get(reverse('deal_completion_prepare',args=[self.deal.pk])).status_code,404)
        self.finish();self.client.force_login(self.users['viewer'])
        self.assertEqual(self.client.get(reverse('deal_completion',args=[self.deal.pk])).status_code,200)

    def test_stale_http_review_preserves_notes_and_requires_reconfirmation(self):
        token=self.token();self.deal.sale_price=Decimal('13000');self.deal.revision+=1;self.deal.save()
        response=self.post(token)
        self.assertEqual(response.status_code,409)
        self.assertContains(response,'Practice reminders remain recorded.',status_code=409)
        self.assertFalse(response.context['form']['reviewed'].value())
        self.assertFalse(response.context['form']['demo_confirmed'].value())
        self.assertFalse(DemoDealCompletion.objects.exists())
        fresh=response.context['form']['preview_token'].value()
        self.assertEqual(self.post(fresh).status_code,302)

    def test_bad_token_is_refreshed_and_successful_post_retries(self):
        self.assertEqual(self.post('invalid').status_code,400)
        token=self.token();response=self.post(token)
        self.assertRedirects(response,reverse('deal_completion',args=[self.deal.pk]))
        self.assertRedirects(self.post(token),reverse('deal_completion',args=[self.deal.pk]))
        self.assertEqual(DemoDealCompletion.objects.count(),1)

    def test_completion_hides_from_active_and_blocks_all_fact_edit_paths(self):
        self.finish()
        self.assertEqual(self.client.get(reverse('deals')).context['page_obj'].paginator.count,0)
        self.assertEqual(self.client.get(reverse('deals'),{'scope':'completed'}).context['page_obj'].paginator.count,1)
        self.assertEqual(self.client.get(reverse('deals'),{'scope':'all'}).context['page_obj'].paginator.count,1)
        for route in ['deal_detail','deal_edit','deal_review']:
            self.assertRedirects(self.client.get(reverse(route,args=[self.deal.pk])),reverse('deal_completion',args=[self.deal.pk]))
        for route in ['deal_detail','deal_edit','draft_lifecycle']:
            self.assertEqual(self.client.post(reverse(route,args=[self.deal.pk]),{}).status_code,409)
        self.assertEqual(self.client.post(reverse('trade_edit',args=[self.deal.pk]),{}).status_code,403)
        with self.assertRaises(ValidationError):persist_draft(self.deal,actor=self.user)

    def test_database_guards_frozen_rows_and_children(self):
        record=self.finish()
        mutations=[lambda:DraftDeal.objects.filter(pk=self.deal.pk).update(sale_price=1),lambda:DemoDealCompletion.objects.filter(pk=record.pk).update(review_notes='Rewrite'),lambda:DemoDealPacket.objects.filter(pk=record.packet_id).update(html='Rewrite'),lambda:DealEvent.objects.filter(deal=self.deal).update(snapshot={}),lambda:DraftFinanceProposal.objects.create(deal=self.deal,kind='bhph'),lambda:DraftTradeIn.objects.create(deal=self.deal,vin='SYNTHETIC-TRADE')]
        for mutate in mutations:
            with self.assertRaises(DatabaseError),transaction.atomic():mutate()

    def test_audit_failure_rolls_back_packet_and_completion(self):
        with patch('deals.completion.DealEvent.objects.create',side_effect=RuntimeError('Audit unavailable')):
            with self.assertRaises(RuntimeError):self.finish()
        self.assertFalse(DemoDealCompletion.objects.exists());self.assertFalse(DemoDealPacket.objects.exists())
        self.deal.sale_price=Decimal('11999');self.deal.save()

    def test_corrupt_related_records_and_tax_metadata_fail_closed(self):
        foreign=Vehicle.objects.create(dealership=self.other,stock_number='PRIVATE',year=2020,make='Other',model='Private')
        self.deal.vehicle=foreign;self.deal.save()
        from django.http import Http404
        with self.assertRaises(Http404):self.source()
        self.deal.vehicle=self.vehicle;self.deal.tax_context=[];self.deal.save()
        with self.assertRaises(CompletionChanged):self.source()

    def test_in_memory_packet_corruption_detected(self):
        record=self.finish();record.packet.html='tampered'
        with self.assertRaises(CompletionChanged):verified_snapshot(record)

    def test_existing_child_and_history_rows_cannot_be_changed_or_reparented(self):
        proposal=DraftFinanceProposal.objects.create(deal=self.deal,kind='bhph')
        trade=DraftTradeIn.objects.create(deal=self.deal,vin='PRACTICE-TRADE')
        self.finish()
        another=DraftDeal.objects.create(dealership=self.dealer,vehicle=self.vehicle,buyer=self.buyer,deal_type='cash',sale_price=100)
        mutations=[lambda:DraftFinanceProposal.objects.filter(pk=proposal.pk).update(payment_count=12),
                   lambda:DraftFinanceProposal.objects.filter(pk=proposal.pk).update(deal=another),
                   lambda:DraftTradeIn.objects.filter(pk=trade.pk).update(vin='DIFFERENT'),
                   lambda:DraftTradeIn.objects.filter(pk=trade.pk).update(deal=another),
                   lambda:DealEvent.objects.filter(deal=self.deal).delete(),
                   lambda:DemoDealCompletion.objects.filter(deal=self.deal).delete()]
        for mutate in mutations:
            with self.assertRaises(DatabaseError),transaction.atomic():mutate()

    def test_database_rejects_packet_from_another_deal(self):
        from documents.packets import packet_source,source_digest,create_packet
        another=DraftDeal.objects.create(dealership=self.dealer,vehicle=self.vehicle,buyer=self.buyer,deal_type='cash',sale_price=100)
        source=packet_source(dealership_id=self.dealer.pk,deal_id=another.pk)
        packet,_=create_packet(dealership_id=self.dealer.pk,deal_id=another.pk,actor=self.user,creation_key=uuid4(),expected_source=source_digest(source))
        with self.assertRaises(DatabaseError),transaction.atomic():
            DemoDealCompletion.objects.create(deal=self.deal,packet=packet,source_revision=self.deal.revision,source_sha256=packet.source_sha256,artifact_sha256=packet.artifact_sha256,review_sha256='a'*64,metadata={},actor=self.user)

    def test_deal_and_trade_notes_are_frozen_separately_from_review_notes(self):
        self.deal.notes='Practice agreed delivery note';self.deal.save()
        DraftTradeIn.objects.create(deal=self.deal,vin='PRACTICE-NOTES',notes='Practice trade condition note')
        record=self.finish()
        self.assertEqual(record.metadata['deal_notes'],'Practice agreed delivery note')
        self.assertEqual(record.metadata['trade_notes'],'Practice trade condition note')
        response=self.client.get(reverse('deal_completion',args=[self.deal.pk]))
        self.assertContains(response,'Practice agreed delivery note');self.assertContains(response,'Practice trade condition note')

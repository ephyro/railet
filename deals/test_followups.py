# SPDX-License-Identifier: MPL-2.0
import uuid
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from core.models import Dealership,Membership
from customers.models import Customer
from inventory.models import Vehicle
from .models import DraftDeal,DealFollowUp,FollowUpEvent


class FollowUpTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer=Dealership.objects.create(name='Synthetic follow-up dealer')
        cls.other=Dealership.objects.create(name='Other dealer')
        cls.users={}
        for name,role,dealer in [('staff','staff',cls.dealer),('coworker','owner',cls.dealer),('viewer','viewer',cls.dealer),('foreign','owner',cls.other)]:
            user=get_user_model().objects.create_user(name);cls.users[name]=user
            Membership.objects.create(user=user,role=role,dealership=dealer)
        vehicle=Vehicle.objects.create(dealership=cls.dealer,stock_number='SYN-FOLLOW',year=2020,make='Synthetic',model='Sedan')
        buyer=Customer.objects.create(dealership=cls.dealer,first_name='Riley',last_name='Demo')
        cls.deal=DraftDeal.objects.create(dealership=cls.dealer,vehicle=vehicle,buyer=buyer)

    def setUp(self):
        self.client.force_login(self.users['staff'])
        self.url=reverse('followup_create',args=[self.deal.pk])
        self.data={'title':'Review synthetic stock details','detail':'Internal reminder using invented data.','assigned_to':self.users['staff'].pk,'due_on':'2026-11-10','revision':1,'creation_key':str(uuid.uuid4())}

    def create(self):
        response=self.client.post(self.url,self.data)
        self.assertEqual(response.status_code,302)
        return DealFollowUp.objects.get()

    def edit(self,task,**changes):
        return self.client.post(reverse('followup_edit',args=[self.deal.pk,task.pk]),{**self.data,**changes})

    def test_create_and_retry_do_not_duplicate_or_change_parent(self):
        task=self.create();self.assertEqual(self.client.post(self.url,self.data).status_code,302)
        self.assertEqual(DealFollowUp.objects.count(),1);self.assertEqual(FollowUpEvent.objects.count(),1)
        self.deal.refresh_from_db();self.assertEqual(self.deal.revision,1);self.assertEqual(self.deal.events.count(),0)
        self.assertEqual(task.assigned_to,self.users['staff'])

    def test_creation_key_conflict_does_not_change_original(self):
        self.create()
        response=self.client.post(self.url,{**self.data,'title':'Changed retry'})
        self.assertEqual(response.status_code,409)
        self.assertEqual(DealFollowUp.objects.get().title,self.data['title'])

    def test_complete_reopen_and_reassign_preserve_history(self):
        task=self.create()
        self.assertEqual(self.edit(task,completed='on').status_code,302)
        task.refresh_from_db();self.assertIsNotNone(task.completed_at);self.assertEqual(task.completed_by,self.users['staff'])
        self.assertEqual(task.revision,2)
        self.assertEqual(self.edit(task,revision=2,assigned_to=self.users['coworker'].pk).status_code,302)
        task.refresh_from_db();self.assertIsNone(task.completed_at);self.assertEqual(task.assigned_to,self.users['coworker'])
        self.assertEqual(list(task.events.values_list('action',flat=True)),['reopened','completed','created'])
        self.assertIsNotNone(task.events.get(action='completed').snapshot['completed_at'])

    def test_stale_edit_is_preserved_and_noop_adds_no_event(self):
        task=self.create();self.assertEqual(self.edit(task).status_code,302)
        self.assertEqual(task.events.count(),1)
        self.edit(task,title='Updated')
        response=self.edit(task,title='Stale proposal')
        self.assertEqual(response.status_code,409)
        self.assertContains(response,'Stale proposal',status_code=409)
        task.refresh_from_db();self.assertEqual(task.title,'Updated')

    def test_invalid_or_foreign_or_viewer_assignee_is_rejected(self):
        for name in ('foreign','viewer'):
            response=self.client.post(self.url,{**self.data,'assigned_to':self.users[name].pk})
            self.assertEqual(response.status_code,200);self.assertTrue(response.context['form'].errors)
        self.assertEqual(DealFollowUp.objects.count(),0)

    def test_role_scope_and_cross_dealer_detail(self):
        task=self.create()
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.client.get(reverse('followup_detail',args=[task.pk])).status_code,200)
        self.assertEqual(self.client.post(self.url,self.data).status_code,403)
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(reverse('followup_detail',args=[task.pk])).status_code,404)
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.assertEqual(len(self.client.get(reverse('followups')).context['page']),0)

    def test_home_mine_completion_and_overdue_filters(self):
        task=self.create();task.due_on=timezone.localdate()-timedelta(days=1);task.save()
        home=self.client.get(reverse('today'));self.assertContains(home,'Overdue:');self.assertContains(home,self.data['title'])
        mine=self.client.get(reverse('followups'),{'mine':'1'});self.assertEqual(len(mine.context['page']),1)
        self.edit(task,completed='on')
        self.assertEqual(len(self.client.get(reverse('followups')).context['page']),0)
        self.assertEqual(len(self.client.get(reverse('followups'),{'scope':'completed'}).context['page']),1)
        self.assertNotContains(self.client.get(reverse('today')),self.data['title'])

    def test_archived_deals_allow_internal_followups_without_restoration(self):
        self.deal.archived_at=timezone.now();self.deal.save()
        self.create();self.deal.refresh_from_db();self.assertIsNotNone(self.deal.archived_at)
        self.assertContains(self.client.get(reverse('followups')),'Archived draft')

    def test_audit_failure_rolls_back_create(self):
        with patch('deals.followups.FollowUpEvent.objects.create',side_effect=RuntimeError('synthetic audit failure')):
            with self.assertRaises(RuntimeError):self.client.post(self.url,self.data)
        self.assertEqual(DealFollowUp.objects.count(),0)

    def test_text_escaping_csrf_and_read_method_controls(self):
        self.data['detail']='<script>Synthetic</script>';task=self.create()
        response=self.client.get(reverse('followup_detail',args=[task.pk]))
        self.assertContains(response,'&lt;script&gt;Synthetic&lt;/script&gt;');self.assertIn('no-store',response['Cache-Control'])
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.users['staff'])
        self.assertEqual(strict.post(self.url,self.data).status_code,403)
        self.assertEqual(self.client.post(reverse('followup_detail',args=[task.pk])).status_code,405)

    def test_invalid_data_preserves_title_and_bounded_fields(self):
        response=self.client.post(self.url,{**self.data,'due_on':'not-a-date'})
        self.assertContains(response,self.data['title']);self.assertTrue(response.context['form'].errors)
        self.assertEqual(DealFollowUp.objects.count(),0)

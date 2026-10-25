# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import connection,connections,close_old_connections
from django.test import Client,TransactionTestCase,override_settings
from django.urls import reverse
from core.models import Dealership,Membership
from customers.models import Customer
from inventory.models import Vehicle
from deals.models import DraftDeal,DealFollowUp,FollowUpEvent
from documents.models import DemoDealPacket
from feedback.models import FeedbackReport


@skipUnless(connection.vendor=='postgresql','Integration concurrency requires PostgreSQL')
@override_settings(DEMO_PACKETS_ENABLED=True)
class NewWorkflowConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.dealer=Dealership.objects.create(name='Synthetic integration dealer')
        self.user=get_user_model().objects.create_user('integration-staff')
        Membership.objects.create(user=self.user,dealership=self.dealer,role='owner')
        vehicle=Vehicle.objects.create(dealership=self.dealer,stock_number='SYN-INTEGRATION',year=2020,make='Synthetic',model='Sedan')
        buyer=Customer.objects.create(dealership=self.dealer,first_name='Riley',last_name='Demo')
        self.deal=DraftDeal.objects.create(dealership=self.dealer,vehicle=vehicle,buyer=buyer)
        self.client.force_login(self.user)

    def race(self,requests):
        barrier=Barrier(len(requests))
        def submit(item):
            close_old_connections()
            try:
                client=Client();client.force_login(get_user_model().objects.get(pk=self.user.pk))
                barrier.wait(timeout=10)
                return client.post(item[0],item[1]).status_code
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            futures=[pool.submit(submit,item) for item in requests]
            return [future.result(timeout=30) for future in futures]

    def test_same_feedback_preview_commits_one_report(self):
        preview=self.client.post(reverse('feedback_create'),{'kind':'bug','area':'general','subject':'Synthetic retry','expected':'One report','actual':'Retrying synthetic report','privacy_checked':'on','submission_key':str(uuid4())})
        request=(reverse('feedback_confirm'),{'preview_token':preview.context['token'],'action':'save'})
        self.assertEqual(self.race([request,request]),[302,302])
        self.assertEqual(FeedbackReport.objects.count(),1)

    def test_same_packet_preview_commits_one_artifact(self):
        url=reverse('demo_packet_list',args=[self.deal.pk]);token=self.client.get(url).context['token']
        request=(url,{'preview_token':token})
        self.assertEqual(self.race([request,request]),[302,302])
        self.assertEqual(DemoDealPacket.objects.count(),1)

    def test_archive_retry_commits_one_event(self):
        request=(reverse('draft_lifecycle',args=[self.deal.pk]),{'revision':1,'action':'archive','reason':'Synthetic simultaneous archive'})
        self.assertCountEqual(self.race([request,request]),[302,409])
        self.assertEqual(self.deal.events.count(),1)

    def test_same_followup_key_commits_one_task_and_event(self):
        request=(reverse('followup_create',args=[self.deal.pk]),{'title':'Synthetic follow-up','detail':'One task','revision':1,'creation_key':str(uuid4()),'assigned_to':self.user.pk})
        self.assertEqual(self.race([request,request]),[302,302])
        self.assertEqual(DealFollowUp.objects.count(),1);self.assertEqual(FollowUpEvent.objects.count(),1)

    def test_archive_and_packet_capture_have_a_valid_serial_order(self):
        url=reverse('demo_packet_list',args=[self.deal.pk]);token=self.client.get(url).context['token']
        statuses=self.race([(url,{'preview_token':token}),(reverse('draft_lifecycle',args=[self.deal.pk]),{'revision':1,'action':'archive','reason':'Synthetic archive race'})])
        self.assertEqual(statuses[1],302)
        self.assertIn(statuses[0],(302,409))
        self.assertEqual(DemoDealPacket.objects.count(),1 if statuses[0]==302 else 0)
        self.deal.refresh_from_db();self.assertIsNotNone(self.deal.archived_at)

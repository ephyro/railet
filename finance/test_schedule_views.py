# SPDX-License-Identifier: MPL-2.0
from datetime import date
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import DatabaseError,transaction
from django.test import TestCase,override_settings
from django.urls import reverse
from core.models import Dealership,Membership
from customers.models import Customer
from .models import DemoSchedule,DemoPosting
from .services import open_book


@override_settings(DEMO_LEDGER_ENABLED=True)
class ScheduleWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer=Dealership.objects.create(name='Synthetic schedule dealer')
        cls.other=Dealership.objects.create(name='Other dealer')
        cls.users={}
        for name,role,dealer in [('staff','staff',cls.dealer),('viewer','viewer',cls.dealer),('foreign','owner',cls.other)]:
            user=get_user_model().objects.create_user(name);cls.users[name]=user
            Membership.objects.create(user=user,dealership=dealer,role=role)
        customer=Customer.objects.create(dealership=cls.dealer,first_name='Riley',last_name='Demo')
        cls.book,_=open_book(dealership_id=cls.dealer.pk,customer_id=customer.pk,actor=cls.users['staff'],label='DEMO schedule cases',source_reference='Invented schedule reference',opening_on=date(2026,1,1),opening_amount='1000.00',request_key=uuid4())

    def setUp(self):
        self.client.force_login(self.users['staff']);self.url=reverse('schedule_new',args=[self.book.pk])
        self.data={'method':'precomputed','frequency':'monthly','first_due_on':'2026-02-01','count':'3','finance_charge':'100.00','synthetic_confirmed':'on'}

    def preview(self,data=None):
        response=self.client.post(self.url,data or self.data)
        self.assertEqual(response.status_code,200)
        return response

    def save(self,token,**extra):return self.client.post(reverse('schedule_confirm'),{'preview_token':token,'action':'save',**extra})

    def test_explicit_choice_preview_and_idempotent_frozen_save_without_postings(self):
        form=self.client.get(self.url).context['form'];self.assertIsNone(form['method'].value())
        self.assertEqual(form['frequency'].value(),'monthly')
        preview=self.preview();self.assertEqual(DemoSchedule.objects.count(),0)
        self.assertEqual(preview.context['result']['total_payments_cents'],110000)
        response=self.save(preview.context['token']);self.assertEqual(response.status_code,302)
        again=self.save(preview.context['token']);self.assertEqual(response.url,again.url)
        illustration=DemoSchedule.objects.get()
        self.assertEqual(illustration.result['rows'][-1]['payment_cents'],36666)
        with patch('finance.schedule_services.calculate_for_book',side_effect=AssertionError('Do not regenerate saved results')):
            self.assertEqual(self.client.get(response.url).status_code,200)
            self.assertEqual(self.save(preview.context['token']).status_code,302)
        self.assertEqual(DemoPosting.objects.count(),1)

    def test_daily_simple_independent_reference_preview(self):
        preview=self.preview({'method':'simple_daily','frequency':'semimonthly','first_due_on':'2026-01-11','first_day':'11','second_day':'21','count':'2','contract_rate':'36.5','regular_payment':'510.00','synthetic_confirmed':'on'})
        result=preview.context['result']
        self.assertEqual(result['finance_charge_cents'],1500)
        self.assertEqual(result['total_payments_cents'],101500)
        self.assertEqual(result['rows'][-1]['payment_cents'],50500)
        self.assertContains(preview,'fixed-365')
        self.save(preview.context['token'])
        self.assertEqual(DemoPosting.objects.count(),1)

    def test_mixed_inputs_missing_consent_and_invalid_calculations_preserve_work(self):
        for extra in ({'contract_rate':'12'},{'synthetic_confirmed':''},{'method':''},{'frequency':'semimonthly'},{'finance_charge':'1.001'}):
            response=self.preview({**self.data,**extra})
            self.assertTrue(response.context['form'].errors)
        self.assertEqual(DemoSchedule.objects.count(),0)

    def test_changed_calculation_requires_fresh_preview(self):
        preview=self.preview()
        with patch('finance.schedule_services.calculate_for_book',return_value={'changed':'synthetic version'}):
            response=self.save(preview.context['token'])
        self.assertEqual(response.status_code,409)
        self.assertEqual(DemoSchedule.objects.count(),0)
        self.assertEqual(response.context['form']['finance_charge'].value(),'100.00')

    def test_edit_preserves_inputs_without_saving(self):
        preview=self.preview();response=self.save(preview.context['token'],action='edit')
        self.assertEqual(response.context['form']['method'].value(),'precomputed')
        self.assertEqual(response.context['form']['finance_charge'].value(),'100.00')
        self.assertEqual(DemoSchedule.objects.count(),0)

    def test_tampered_expired_and_wrong_actor_tokens_fail(self):
        preview=self.preview();self.assertEqual(self.save(preview.context['token']+'x').status_code,400)
        with patch('django.core.signing.time.time',return_value=10):old=self.preview()
        self.assertEqual(self.save(old.context['token']).status_code,400)
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.save(preview.context['token']).status_code,403)
        self.assertEqual(DemoSchedule.objects.count(),0)

    def test_viewer_read_and_foreign_scope(self):
        response=self.save(self.preview().context['token']);url=response.url
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.get(self.url).status_code,403)
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.get(reverse('schedule_list',args=[self.book.pk])).status_code,404)

    def test_database_refuses_update_or_delete_saved_illustration(self):
        self.save(self.preview().context['token']);illustration=DemoSchedule.objects.get()
        for operation in (lambda:DemoSchedule.objects.filter(pk=illustration.pk).update(method='simple_daily'),lambda:DemoSchedule.objects.filter(pk=illustration.pk).delete()):
            with self.assertRaises(DatabaseError),transaction.atomic():operation()
        self.assertEqual(DemoPosting.objects.count(),1)

    @override_settings(DEMO_LEDGER_ENABLED=False)
    def test_gate_disables_schedule_routes(self):
        self.assertEqual(self.client.get(self.url).status_code,403)
        self.assertEqual(self.save('bad').status_code,403)

    def test_saved_rows_are_paginated_and_private(self):
        preview=self.preview({**self.data,'count':'26'})
        response=self.save(preview.context['token'])
        first=self.client.get(response.url);second=self.client.get(response.url,{'page':2})
        self.assertEqual(len(first.context['rows']),25);self.assertEqual(len(second.context['rows']),1)
        self.assertEqual(second.context['rows'][0]['number'],26)
        self.assertIn('no-store',first['Cache-Control'])

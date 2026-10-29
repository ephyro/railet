# SPDX-License-Identifier: MPL-2.0
import json
from datetime import date
from uuid import uuid4
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.urls import reverse
from core.models import SavedView
from . import test_servicing as fixtures
from .models import DemoPosting
from .services import open_book,record_receipt,reverse_receipt,LedgerError
from .schedule_services import calculate_for_book,save_illustration,result_digest
from .servicing_services import select_baseline,projection_for_book

@override_settings(DEMO_LEDGER_ENABLED=True,DEMO_SERVICING_ENABLED=True)
class AccountWorklistTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.ServicingIntegrationTests.setUpTestData.__func__(cls)
        select_baseline(dealership_id=cls.dealer.pk,book_id=cls.book.pk,schedule_id=cls.schedule.pk,actor=cls.users['staff'],reason='Invented worklist baseline',creation_key=uuid4(),expected_digest=cls.schedule.result_sha256)
    def setUp(self):
        self.client.force_login(self.users['staff']);self.url=reverse('ledger_demo_list')
        clock=patch('finance.servicing_services.timezone.localdate',return_value=date(2026,3,2));clock.start();self.addCleanup(clock.stop)
    def create(self,label,*,scheduled=True,first='2026-02-01',amount=None):
        book,_=open_book(dealership_id=self.dealer.pk,customer_id=self.customer.pk,actor=self.users['staff'],label=label,source_reference='Invented worklist reference',opening_on=date(2026,1,1),opening_amount='1000',request_key=uuid4())
        if scheduled:
            inputs={**self.inputs,'first_due_on':first};result=calculate_for_book(book,inputs)
            saved,_=save_illustration(dealership_id=self.dealer.pk,book_id=book.pk,actor=self.users['staff'],inputs=inputs,expected_digest=result_digest(result),creation_key=uuid4())
            select_baseline(dealership_id=self.dealer.pk,book_id=book.pk,schedule_id=saved.pk,actor=self.users['staff'],reason='Invented worklist baseline',creation_key=uuid4(),expected_digest=saved.result_sha256)
        if amount:self.pay(book,amount)
        return book
    def pay(self,book,amount):
        return record_receipt(dealership_id=self.dealer.pk,book_id=book.pk,actor=self.users['staff'],amount=amount,effective_on=date(2026,2,1),reason='Invented worklist payment',request_key=uuid4())[0]
    def get(self,**params):return self.client.get(self.url,params)
    def ids(self,**params):return [b.pk for b in self.get(**params).context['page']]

    def test_filters_match_literal_due_today_current_covered_unknown_and_partial_values(self):
        partial=self.create('Partial synthetic',amount='150');today=self.create('Due today synthetic',first='2026-03-02')
        current=self.create('Current synthetic',amount='250');covered=self.create('Covered synthetic',amount='1000');unknown=self.create('Unknown synthetic',scheduled=False)
        self.assertCountEqual(self.ids(status='past_due'),[self.book.pk,partial.pk])
        self.assertEqual(self.ids(status='due_today'),[today.pk]);self.assertCountEqual(self.ids(status='current'),[current.pk,covered.pk])
        self.assertEqual(self.ids(status='uncalculated'),[unknown.pk])
        response=self.get(status='past_due',sort='oldest_due');books=list(response.context['page'])
        self.assertEqual([b.pk for b in books],[self.book.pk,partial.pk]);self.assertEqual([b.simulation['amount_due_cents'] for b in books],[20000,5000])
        self.assertContains(response,'Feb 1, 2026');self.assertContains(response,'Mar 1, 2026')
        self.assertNotIn('rows',books[0].simulation);self.assertNotIn('coverage',books[0].simulation)

    def test_filter_and_sort_apply_before_pagination_and_ties_are_stable(self):
        for number in range(26):self.create(f'Late pagination {number}')
        self.create('Unknown pagination',scheduled=False)
        first=self.get(status='past_due',sort='oldest_due');second=self.get(status='past_due',sort='oldest_due',page=2)
        self.assertEqual(first.context['page'].paginator.count,27)
        self.assertEqual(len(first.context['page']),25);self.assertEqual(len(second.context['page']),2)
        ids=[b.pk for b in first.context['page']]+[b.pk for b in second.context['page']]
        self.assertEqual(ids,sorted(ids));self.assertEqual(len(set(ids)),27)
        self.assertContains(first,'status=past_due');self.assertContains(first,'sort=oldest_due')

    def test_older_matching_account_is_not_lost_beyond_default_page(self):
        for number in range(26):self.create(f'Unknown later {number}',scheduled=False)
        self.assertNotIn(self.book.pk,self.ids())
        self.assertEqual(self.ids(status='past_due'),[self.book.pk])

    def test_saved_status_views_remain_dynamic_and_private(self):
        response=self.client.post(reverse('saved_view_create',args=['accounts']),{'name':'Late synthetic accounts','parameters':json.dumps({'status':['past_due'],'sort':['oldest_due']})})
        saved=SavedView.objects.get();self.assertEqual(response.status_code,302)
        self.assertEqual(self.ids(view=saved.pk),[self.book.pk]);receipt=self.pay(self.book,'200')
        self.assertEqual(self.ids(view=saved.pk),[])
        reverse_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,posting_id=receipt.pk,actor=self.users['staff'],effective_on=date(2026,3,2),reason='Invented worklist correction',request_key=uuid4())
        self.assertEqual(self.ids(view=saved.pk),[self.book.pk])
        self.client.force_login(self.users['viewer']);self.assertEqual(self.get(view=saved.pk).status_code,404)

    def test_search_and_typed_rules_survive_tab_links_and_filtering(self):
        self.create('Other unknown',scheduled=False)
        params={'q':'Riley','filter_field':'opening','filter_op':'eq','filter_value':'2026-01-01','scope':'unlinked','status':'past_due'}
        response=self.get(**params);self.assertEqual([b.pk for b in response.context['page']],[self.book.pk])
        for tab in response.context['status_tabs']:
            self.assertIn('q=Riley',tab['query']);self.assertIn('scope=unlinked',tab['query']);self.assertIn('filter_field=opening',tab['query'])
        self.assertEqual(self.ids(status='past_due',q='no such invented customer'),[])
        self.assertEqual(self.ids(status='past_due',scope='linked'),[])

    def test_invalid_or_missing_baseline_stays_unknown_never_green(self):
        original=projection_for_book
        def fail(book,**kwargs):
            if book.pk==self.book.pk:raise LedgerError('Invented source verification failure')
            return original(book,**kwargs)
        with patch('finance.servicing_services.projection_for_book',side_effect=fail):
            self.assertEqual(self.ids(status='past_due'),[]);self.assertEqual(self.ids(status='current'),[])
            response=self.get(status='uncalculated');self.assertEqual([b.pk for b in response.context['page']],[self.book.pk]);self.assertContains(response,'Status unavailable')

    def test_limits_and_invalid_status_fail_closed_with_actionable_errors(self):
        self.create('Another invented account',scheduled=False)
        with patch('finance.account_worklist.MAX_ACCOUNTS',1):
            response=self.get(status='past_due');self.assertEqual(list(response.context['page']),[])
            self.assertContains(response,'Narrow the customer or vehicle search');self.assertTrue(response.context['filter_state'].errors)
            self.assertEqual(self.ids(status='past_due',q=f'#{self.book.pk}'),[self.book.pk])
        self.assertEqual(self.ids(status='fake'),[])
        self.pay(self.book,'1')
        with patch('finance.servicing_services.MAX_LIST_POSTINGS',1):
            response=self.get(status='past_due');self.assertContains(response,'Too much journal activity');self.assertEqual(list(response.context['page']),[])
        with patch('finance.account_worklist.attach_list_status',side_effect=LedgerError('Too much journal activity; narrow the search.')):
            response=self.get(sort='oldest_due');self.assertContains(response,'Too much journal activity');self.assertEqual(list(response.context['page']),[])

    def test_roles_gate_and_read_only_action_links(self):
        before=list(DemoPosting.objects.values())
        response=self.get(status='past_due');self.assertContains(response,reverse('ledger_demo_receipt',args=[self.book.pk]))
        self.assertEqual(list(DemoPosting.objects.values()),before)
        self.client.force_login(self.users['viewer']);response=self.get(status='past_due')
        self.assertContains(response,'Open account');self.assertNotContains(response,reverse('ledger_demo_receipt',args=[self.book.pk]))
        self.client.force_login(self.users['foreign']);self.assertEqual(self.ids(status='past_due'),[])
        self.client.force_login(self.users['staff'])
        with override_settings(DEMO_SERVICING_ENABLED=False):
            response=self.get();self.assertNotContains(response,'Oldest overdue first');self.assertNotContains(response,'Demo account status')
            self.assertEqual(self.ids(status='past_due'),[])
        with override_settings(DEMO_LEDGER_ENABLED=False):self.assertEqual(self.get(status='past_due').status_code,403)

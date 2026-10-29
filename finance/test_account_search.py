# SPDX-License-Identifier: MPL-2.0
import json
from uuid import uuid4
from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from core.models import Membership,SavedView
from customers.models import Customer
from .models import DemoBook
from .services import open_book
from .account_services import link_draft
from .schedule_services import result_digest
from deals.account_context import account_draft_snapshot
from . import test_accounts as fixtures


@override_settings(DEMO_LEDGER_ENABLED=True)
class AccountSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.AccountWorkspaceTests.setUpTestData.__func__(cls)
        cls.customer.phone='(305) 555-0100';cls.customer.save()
        cls.customer.email='riley@example.invalid';cls.customer.save()
        cls.vehicle.vin='SYNTHETIC-VIN-SEARCH';cls.vehicle.save()
        link_draft(dealership_id=cls.dealer.pk,book_id=cls.book.pk,deal_id=cls.deal.pk,actor=cls.users['staff'],expected_digest=result_digest(account_draft_snapshot(cls.deal)))
        other_customer=Customer.objects.create(dealership=cls.dealer,first_name='Alex',last_name='Unlinked')
        cls.unlinked,_=open_book(dealership_id=cls.dealer.pk,customer_id=other_customer.pk,actor=cls.users['staff'],label='Unlinked synthetic account',source_reference='Synthetic source',opening_on=date(2025,1,1),opening_amount='500',request_key=uuid4())
        foreign_customer=Customer.objects.create(dealership=cls.other,first_name='Foreign',last_name='Secret')
        cls.foreign,_=open_book(dealership_id=cls.other.pk,customer_id=foreign_customer.pk,actor=cls.users['foreign'],label='FOREIGN-PRIVATE-ACCOUNT',source_reference='Synthetic foreign source',opening_on=date(2026,1,1),opening_amount='800',request_key=uuid4())

    def setUp(self):
        self.client.force_login(self.users['staff']);self.url=reverse('ledger_demo_list')

    def ids(self,params):
        response=self.client.get(self.url,params);self.assertEqual(response.status_code,200)
        return {book.pk for book in response.context['page']}

    def test_customer_vehicle_stock_vin_phone_and_account_search(self):
        for query in ('Riley','Riley Demo','riley@example.invalid','305-555-0100','Synthetic Sedan','DEMO-ACCOUNT','VIN-SEARCH',f'#{self.book.pk}'):
            with self.subTest(query=query):self.assertEqual(self.ids({'q':query}),{self.book.pk})
        self.assertEqual(self.ids({'q':'9'*200}),set())
        self.assertEqual(self.ids({'q':'missing vehicle'}),set())

    def test_vehicle_search_uses_frozen_linked_identity(self):
        self.vehicle.stock_number='Changed-current-stock';self.vehicle.model='Changed-current-model';self.vehicle.save()
        self.assertEqual(self.ids({'q':'DEMO-ACCOUNT'}),{self.book.pk})
        self.assertEqual(self.ids({'q':'Changed-current-stock'}),set())
        self.assertContains(self.client.get(self.url),'As saved when linked')

    def test_quick_scopes_and_typed_rules(self):
        self.assertEqual(self.ids({'scope':'linked'}),{self.book.pk})
        self.assertEqual(self.ids({'scope':'unlinked'}),{self.unlinked.pk})
        for field,value in [('linked','true'),('method','precomputed'),('frequency','monthly'),('stock','DEMO-ACCOUNT')]:
            self.assertEqual(self.ids({'filter_field':field,'filter_op':'eq','filter_value':value}),{self.book.pk})
        self.assertEqual(self.ids({'filter_field':'opening','filter_op':'lte','filter_value':'2025-12-31'}),{self.unlinked.pk})

    def test_all_any_matching_and_invalid_filters_fail_closed(self):
        params={'filter_field':['linked','last_name'],'filter_op':['eq','eq'],'filter_value':['true','Unlinked'],'match':'all'}
        self.assertEqual(self.ids(params),set())
        params['match']='any';self.assertEqual(self.ids(params),{self.book.pk,self.unlinked.pk})
        for invalid in ({'scope':'foreign'},{'sort':'secret'},{'filter_field':'dealership_id','filter_op':'eq','filter_value':str(self.other.pk)}):
            self.assertEqual(self.ids(invalid),set())
            self.assertTrue(self.client.get(self.url,invalid).context['filter_state'].errors)

    def test_foreign_results_cannot_escape_scope(self):
        self.assertEqual(self.ids({'q':'FOREIGN-PRIVATE-ACCOUNT'}),set())
        self.assertEqual(self.ids({'q':f'#{self.foreign.pk}'}),set())
        self.assertNotContains(self.client.get(self.url),'FOREIGN-PRIVATE-ACCOUNT')
        self.assertIn('no-store',self.client.get(self.url)['Cache-Control'])

    def test_saved_view_is_dynamic_private_and_gate_aware(self):
        response=self.client.post(reverse('saved_view_create',args=['accounts']),{'name':'My linked accounts','parameters':json.dumps({'scope':['linked'],'q':['Riley']})})
        self.assertEqual(response.status_code,302);saved=SavedView.objects.get()
        self.assertEqual(self.ids({'view':saved.pk}),{self.book.pk})
        self.customer.first_name='Changed';self.customer.email='changed@example.invalid';self.customer.save()
        self.assertEqual(self.ids({'view':saved.pk}),set())
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.client.get(self.url,{'view':saved.pk}).status_code,404)
        self.assertEqual(self.client.post(reverse('saved_view_delete',args=[saved.pk])).status_code,404)
        self.client.force_login(self.users['staff'])
        with override_settings(DEMO_LEDGER_ENABLED=False):
            self.assertEqual(self.client.get(self.url).status_code,403)
            self.assertEqual(self.client.get(reverse('saved_view_create',args=['accounts'])).status_code,404)

    def test_viewer_can_save_filters_without_financial_write_access(self):
        self.client.force_login(self.users['viewer'])
        response=self.client.post(reverse('saved_view_create',args=['accounts']),{'name':'Unlinked','parameters':json.dumps({'scope':['unlinked']})})
        self.assertEqual(response.status_code,302)
        self.assertEqual(DemoBook.objects.count(),3)
        self.assertEqual(self.ids({'view':SavedView.objects.get().pk}),{self.unlinked.pk})

    def test_pagination_keeps_query_scope_and_sort(self):
        for number in range(26):
            open_book(dealership_id=self.dealer.pk,customer_id=self.unlinked.customer_id,actor=self.users['staff'],label=f'Synthetic pagination {number}',source_reference='Invented pagination fixture',opening_on=date(2025,1,1),opening_amount='1',request_key=uuid4())
        response=self.client.get(self.url,{'q':'pagination','scope':'unlinked','sort':'opening'})
        self.assertEqual(len(response.context['page']),25)
        self.assertContains(response,'scope=unlinked')
        next_page=self.client.get(self.url,{'q':'pagination','scope':'unlinked','sort':'opening','page':2})
        self.assertEqual(len(next_page.context['page']),1)
        self.assertEqual(next_page.context['page'].paginator.count,26)

    def test_activity_uses_integer_journal_amounts_and_retains_corrected_latest_receipt(self):
        from .services import record_receipt, reverse_receipt
        first,_ = record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.users['staff'],amount='19.99',effective_on=date(2026,2,3),reason='Synthetic first receipt',request_key=uuid4())
        latest,_ = record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.users['staff'],amount='5.01',effective_on=date(2026,2,2),reason='Synthetic later entry with earlier effective date',request_key=uuid4())
        response=self.client.get(self.url)
        books={book.pk:book for book in response.context['page']}
        self.assertEqual(books[self.book.pk].activity_unapplied_cents,2500)
        self.assertEqual(books[self.book.pk].latest_receipt_id,latest.pk)
        self.assertEqual(books[self.book.pk].latest_receipt_on,date(2026,2,2))
        self.assertEqual(books[self.unlinked.pk].activity_unapplied_cents,0)
        self.assertIsNone(books[self.unlinked.pk].latest_receipt_id)
        self.assertNotIn(self.foreign.pk,books)
        reverse_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,posting_id=latest.pk,actor=self.users['staff'],effective_on=date(2026,2,4),reason='Synthetic linked correction',request_key=uuid4())
        response=self.client.get(self.url);book=next(book for book in response.context['page'] if book.pk==self.book.pk)
        self.assertEqual(book.activity_unapplied_cents,1999)
        self.assertEqual(book.latest_receipt_cents,501)
        self.assertIsNotNone(book.latest_receipt_correction_id)
        self.assertContains(response,'Corrected')
        self.assertContains(self.client.get(reverse('bhph_account',args=[self.book.pk])),'$19.99')
        self.assertContains(response,'$5.01')
        self.assertContains(response,'not an amount due')

    def test_activity_projects_all_accounts_in_one_query(self):
        from .queries import search_accounts,with_account_activity
        with self.assertNumQueries(1):
            books=list(with_account_activity(search_accounts(dealership_id=self.dealer.pk,query='')))
            for book in books:
                str(book.customer)
                if book.has_context:book.account_context.snapshot
        self.assertEqual({book.pk for book in books},{self.book.pk,self.unlinked.pk})

# SPDX-License-Identifier: MPL-2.0
from datetime import datetime,date,timezone as dt_timezone
from uuid import uuid4
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.urls import reverse
from customers.models import Customer
from . import test_accounts as fixtures
from .services import open_book,record_receipt,reverse_receipt
from .payment_register import capture
from .models import DemoPosting


@override_settings(DEMO_LEDGER_ENABLED=True)
class PaymentRegisterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.AccountWorkspaceTests.setUpTestData.__func__(cls)
        with patch('django.utils.timezone.now',return_value=datetime(2026,1,10,17,tzinfo=dt_timezone.utc)):
            cls.receipt,_=record_receipt(dealership_id=cls.dealer.pk,book_id=cls.book.pk,actor=cls.users['staff'],amount='125.50',effective_on=date(2026,1,5),reason='Synthetic January receipt',request_key=uuid4())
        with patch('django.utils.timezone.now',return_value=datetime(2026,2,5,17,tzinfo=dt_timezone.utc)):
            cls.reversal,_=reverse_receipt(dealership_id=cls.dealer.pk,book_id=cls.book.pk,posting_id=cls.receipt.pk,actor=cls.users['staff'],effective_on=date(2026,1,6),reason='Synthetic February correction',request_key=uuid4())
        customer=Customer.objects.create(dealership=cls.other,first_name='Foreign',last_name='Private')
        foreign,_=open_book(dealership_id=cls.other.pk,customer_id=customer.pk,actor=cls.users['foreign'],label='Foreign synthetic account',source_reference='Synthetic foreign',opening_on=date(2026,1,1),opening_amount='500',request_key=uuid4())
        with patch('django.utils.timezone.now',return_value=datetime(2026,1,10,17,tzinfo=dt_timezone.utc)):
            record_receipt(dealership_id=cls.other.pk,book_id=foreign.pk,actor=cls.users['foreign'],amount='999.99',effective_on=date(2026,1,5),reason='FOREIGN-PRIVATE-RECEIPT',request_key=uuid4())

    def setUp(self):
        self.client.force_login(self.users['staff']);self.url=reverse('payment_register')

    def report(self,**changes):
        data={'basis':'recorded','start':'2026-01-01','end':'2026-02-28'};data.update(changes)
        response=self.client.get(self.url,data);self.assertEqual(response.status_code,200)
        return response

    def test_independent_totals_exclude_openings_and_foreign_entries(self):
        page=self.report()
        self.assertEqual(page.context['totals']['receipts_cents'],12550)
        self.assertEqual(page.context['totals']['corrections_cents'],12550)
        self.assertEqual(page.context['totals']['net_cents'],0)
        self.assertEqual(len(page.context['rows']),2)
        self.assertNotContains(page,'FOREIGN-PRIVATE-RECEIPT')
        self.assertIn('no-store',page['Cache-Control'])
        self.assertEqual(self.client.post(self.url).status_code,405)

    def test_recorded_vs_effective_dates_and_negative_range_net(self):
        recorded=self.report(start='2026-02-05',end='2026-02-05')
        self.assertEqual(recorded.context['totals']['receipts_cents'],0)
        self.assertEqual(recorded.context['totals']['net_cents'],-12550)
        self.assertContains(recorded,'-$125.50')
        effective=self.report(basis='effective',start='2026-01-05',end='2026-01-06')
        self.assertEqual(effective.context['totals']['net_cents'],0)
        self.assertEqual(effective.context['page_obj'].paginator.count,2)
        self.assertEqual(self.report(basis='effective',start='2026-02-05',end='2026-02-05').context['page_obj'].paginator.count,0)

    def test_capture_uses_one_read_for_all_rows_and_totals(self):
        with self.assertNumQueries(1):
            entries,totals=capture(dealership_id=self.dealer.pk,start=date(2026,1,1),end=date(2026,2,28),basis='recorded')
        self.assertEqual(len(entries),2)
        self.assertEqual(totals['net_cents'],0)

    def test_dst_recorded_day_uses_local_midnight_boundaries(self):
        for hour,minute,day in ((4,59,8),(5,0,8),(3,59,9),(4,0,9)):
            with patch('django.utils.timezone.now',return_value=datetime(2026,3,day,hour,minute,tzinfo=dt_timezone.utc)):
                record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.users['staff'],amount='1',effective_on=date(2026,3,1),reason='Synthetic DST boundary',request_key=uuid4())
        response=self.report(start='2026-03-08',end='2026-03-08')
        self.assertEqual(response.context['totals']['receipt_count'],2)
        self.assertEqual(response.context['totals']['receipts_cents'],200)

    def test_invalid_ranges_preserve_input_and_hide_totals(self):
        for changes in ({'basis':'unknown'},{'start':'bad-date'},{'start':'2026-02-01','end':'2026-01-01'},{'start':'2026-01-01','end':'2026-05-01'},{'end':'2099-01-01'}):
            response=self.report(**changes)
            self.assertTrue(response.context['form'].errors)
            self.assertIsNone(response.context['totals'])
            self.assertEqual(response.context['rows'],[])
            self.assertContains(response,'No totals are shown')

    def test_oversized_capture_never_shows_partial_totals(self):
        with patch('finance.payment_register.MAX_ROWS',1):
            response=self.report()
        self.assertTrue(response.context['form'].errors)
        self.assertIsNone(response.context['totals'])
        self.assertEqual(response.context['rows'],[])

    def test_viewer_can_read_and_gate_prevents_all_access(self):
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.report().context['page_obj'].paginator.count,2)
        self.assertEqual(DemoPosting.objects.count(),5)
        with override_settings(DEMO_LEDGER_ENABLED=False):self.assertEqual(self.client.get(self.url).status_code,403)
        self.client.force_login(self.users['foreign'])
        page=self.report()
        self.assertEqual(page.context['totals']['receipts_cents'],99999)
        self.assertNotContains(page,'Synthetic January receipt')

    def test_pagination_keeps_entire_capture_totals_and_dates(self):
        for number in range(26):
            with patch('django.utils.timezone.now',return_value=datetime(2026,1,11,17,tzinfo=dt_timezone.utc)):
                record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.users['staff'],amount='1.25',effective_on=date(2026,1,11),reason=f'Synthetic register row {number}',request_key=uuid4())
        response=self.report(start='2026-01-11',end='2026-01-11',page=2)
        self.assertEqual(len(response.context['rows']),1)
        self.assertEqual(response.context['totals']['net_cents'],3250)
        self.assertEqual(response.context['page_obj'].paginator.count,26)
        self.assertContains(response,'start=2026-01-11')
        self.assertEqual(self.report(start='2026-01-11',end='2026-01-11').context['totals'],response.context['totals'])

    def test_receipt_and_correction_links_reach_source_records(self):
        page=self.report()
        link=reverse('bhph_account_receipt',args=[self.book.pk,self.receipt.pk])
        self.assertContains(page,link)
        self.assertEqual(self.client.get(link).status_code,200)

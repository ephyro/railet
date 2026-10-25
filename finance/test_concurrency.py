# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import connection, connections, close_old_connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from core.models import Dealership,Membership
from customers.models import Customer
from .models import DemoBook,DemoPosting
from .services import open_book,record_receipt,reverse_receipt,LedgerError,reconcile


@skipUnless(connection.vendor=='postgresql','Ledger concurrency requires PostgreSQL')
@override_settings(DEMO_LEDGER_ENABLED=True)
class LedgerConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.dealer=Dealership.objects.create(name='Synthetic concurrency dealer')
        self.user=get_user_model().objects.create_user('ledger-race')
        Membership.objects.create(user=self.user,dealership=self.dealer,role='owner')
        self.customer=Customer.objects.create(dealership=self.dealer,first_name='Riley',last_name='Demo')
        self.today=timezone.localdate()
        self.book,_=open_book(dealership_id=self.dealer.pk,customer_id=self.customer.pk,actor=self.user,label='DEMO race',source_reference='Synthetic opening',opening_on=self.today,opening_amount='10000.25',request_key=uuid4())

    def race(self,functions):
        barrier=Barrier(len(functions))
        def run(function):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return function()
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:return list(pool.map(run,functions))

    def test_same_key_receipts_commit_once(self):
        key=uuid4()
        def post():
            obj,created=record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.user,amount='125.50',effective_on=self.today,reason='Synthetic concurrent receipt',request_key=key)
            return obj.pk,created
        results=self.race([post,post])
        self.assertEqual(results[0][0],results[1][0]);self.assertEqual(sum(created for _,created in results),1)
        self.assertEqual(self.book.postings.filter(kind='receipt').count(),1)

    def test_two_keys_cannot_reverse_receipt_twice(self):
        entry,_=record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.user,amount='125.50',effective_on=self.today,reason='Synthetic original',request_key=uuid4())
        def reverse():
            try:
                reverse_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,posting_id=entry.pk,actor=self.user,effective_on=self.today,reason='Synthetic race correction',request_key=uuid4());return 'posted'
            except LedgerError:return 'rejected'
        self.assertCountEqual(self.race([reverse,reverse]),['posted','rejected'])
        result=reconcile(dealership_id=self.dealer.pk,book_id=self.book.pk)
        self.assertEqual(result['net_debit']['cash_control'],0);self.assertTrue(result['balanced'])

    def test_same_opening_key_commits_one_book(self):
        key=uuid4()
        def post():
            book,created=open_book(dealership_id=self.dealer.pk,customer_id=self.customer.pk,actor=self.user,label='DEMO shared opening',source_reference='Synthetic race source',opening_on=self.today,opening_amount='200.00',request_key=key)
            return book.pk,created
        results=self.race([post,post])
        self.assertEqual(results[0][0],results[1][0]);self.assertEqual(sum(created for _,created in results),1)
        self.assertEqual(DemoBook.objects.filter(creation_key=key).count(),1)

# SPDX-License-Identifier: MPL-2.0
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from core.models import Dealership,Membership
from customers.models import Customer
from .models import DemoBook,DemoPosting
from .services import LedgerError,cents,open_book,record_receipt,reverse_receipt,reconcile


@override_settings(DEMO_LEDGER_ENABLED=True)
class LedgerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer=Dealership.objects.create(name='Synthetic ledger dealer')
        cls.other=Dealership.objects.create(name='Other dealer')
        cls.users={}
        for name,role,dealer in [('staff','staff',cls.dealer),('viewer','viewer',cls.dealer),('foreign','owner',cls.other)]:
            user=get_user_model().objects.create_user(name);cls.users[name]=user
            Membership.objects.create(user=user,dealership=dealer,role=role)
        cls.customer=Customer.objects.create(dealership=cls.dealer,first_name='Riley',last_name='Demo')
        cls.foreign_customer=Customer.objects.create(dealership=cls.other,first_name='Other',last_name='Demo')

    def setUp(self):
        self.today=timezone.localdate();self.opening=self.today-timedelta(days=10)
        self.open_args=dict(dealership_id=self.dealer.pk,customer_id=self.customer.pk,actor=self.users['staff'],label='DEMO synthetic opening',source_reference='Invented reference case, not migrated customer debt',opening_on=self.opening,opening_amount='10000.25',request_key=uuid4())

    def open(self):return open_book(**self.open_args)[0]
    def receipt(self,book,amount='125.50',**kwargs):
        args=dict(dealership_id=self.dealer.pk,book_id=book.pk,actor=self.users['staff'],amount=amount,effective_on=self.today,reason='Synthetic manual reference',request_key=uuid4());args.update(kwargs);return record_receipt(**args)

    def test_independent_reference_case_and_full_linked_correction(self):
        book=self.open();first,_=self.receipt(book);self.receipt(book,'74.50')
        balance=reconcile(dealership_id=self.dealer.pk,book_id=book.pk)
        self.assertEqual(balance['net_debit']['principal'],1000025)
        self.assertEqual(balance['net_debit']['cash_control'],20000)
        correction,_=reverse_receipt(dealership_id=self.dealer.pk,book_id=book.pk,posting_id=first.pk,actor=self.users['staff'],effective_on=self.today,reason='Synthetic correction',request_key=uuid4())
        result=reconcile(dealership_id=self.dealer.pk,book_id=book.pk)
        self.assertTrue(result['balanced']);self.assertEqual(result['total_debits_cents'],1032575);self.assertEqual(result['total_credits_cents'],1032575)
        self.assertEqual(result['net_debit']['principal'],1000025)
        self.assertEqual(result['net_debit']['cash_control'],7450);self.assertEqual(result['net_debit']['unapplied'],-7450)
        first.refresh_from_db();self.assertEqual(first.amount_cents,12550);self.assertEqual(correction.reverses_id,first.pk)

    def test_exact_cents_and_invalid_amounts(self):
        self.assertEqual(cents(Decimal('0.01')),1);self.assertEqual(cents('1.00'),100)
        for value in (1.5,True,'NaN','Infinity','0','-1','1.001','1.000000000000000000000000000000000000001','10000000000'):
            with self.subTest(value=value):
                with self.assertRaises(LedgerError):cents(value)

    def test_opening_and_receipt_retries_are_idempotent_and_mismatches_fail(self):
        book=self.open();again,created=open_book(**self.open_args);self.assertEqual(book.pk,again.pk);self.assertFalse(created)
        with self.assertRaises(LedgerError):open_book(**{**self.open_args,'opening_amount':'20'})
        request=uuid4();first,_=self.receipt(book,request_key=request);again,created=self.receipt(book,request_key=request)
        self.assertEqual(first.pk,again.pk);self.assertFalse(created)
        with self.assertRaises(LedgerError):self.receipt(book,'1.00',request_key=request)
        self.assertEqual(book.postings.count(),2)

    def test_reversal_retry_and_duplicate_correction_protection(self):
        book=self.open();receipt,_=self.receipt(book);args=dict(dealership_id=self.dealer.pk,book_id=book.pk,posting_id=receipt.pk,actor=self.users['staff'],effective_on=self.today,reason='Synthetic correction',request_key=uuid4())
        first,_=reverse_receipt(**args);again,created=reverse_receipt(**args);self.assertEqual(first.pk,again.pk);self.assertFalse(created)
        with self.assertRaises(LedgerError):reverse_receipt(**{**args,'request_key':uuid4()})
        with self.assertRaises(LedgerError):reverse_receipt(**{**args,'posting_id':first.pk,'request_key':uuid4()})

    def test_dates_and_provenance_are_explicit(self):
        with self.assertRaises(LedgerError):open_book(**{**self.open_args,'source_reference':' '})
        with self.assertRaises(LedgerError):open_book(**{**self.open_args,'opening_on':self.today+timedelta(days=1)})
        book=self.open()
        for date in (self.opening-timedelta(days=1),self.today+timedelta(days=1)):
            with self.assertRaises(LedgerError):self.receipt(book,effective_on=date)
        self.assertEqual(book.postings.count(),1)

    def test_roles_and_dealership_isolation(self):
        for name in ('viewer','foreign'):
            with self.assertRaises(PermissionDenied):open_book(**{**self.open_args,'actor':self.users[name]})
        with self.assertRaises(LedgerError):open_book(**{**self.open_args,'customer_id':self.foreign_customer.pk})
        book=self.open()
        with self.assertRaises(DemoBook.DoesNotExist):record_receipt(dealership_id=self.other.pk,book_id=book.pk,actor=self.users['foreign'],amount='1',effective_on=self.today,reason='Synthetic',request_key=uuid4())
        with self.assertRaises(DemoBook.DoesNotExist):reconcile(dealership_id=self.other.pk,book_id=book.pk)

    @override_settings(DEMO_LEDGER_ENABLED=False)
    def test_gate_disables_all_mutations_and_reconciliation(self):
        with self.assertRaises(PermissionDenied):self.open()
        with self.assertRaises(PermissionDenied):self.receipt(type('Book',(),{'pk':1})())
        with self.assertRaises(PermissionDenied):reconcile(dealership_id=self.dealer.pk,book_id=1)

    def test_posted_book_and_journal_cannot_be_updated_or_deleted(self):
        book=self.open();posting=book.postings.get()
        for function in (lambda:DemoBook.objects.filter(pk=book.pk).update(label='altered'),lambda:DemoPosting.objects.filter(pk=posting.pk).update(amount_cents=1),lambda:DemoPosting.objects.filter(pk=posting.pk).delete()):
            with self.assertRaises(DatabaseError),transaction.atomic():function()
        posting.refresh_from_db();self.assertEqual(posting.amount_cents,1000025)

    def test_db_constraints_reject_unbalanced_pair_and_zero(self):
        book=self.open()
        for amount,debit,credit in [(0,'cash_control','unapplied'),(100,'principal','unapplied')]:
            with self.assertRaises(DatabaseError),transaction.atomic():
                DemoPosting.objects.create(book=book,kind='receipt',amount_cents=amount,debit=debit,credit=credit,actor=self.users['staff'],reason='Synthetic invalid posting',effective_on=self.today)

    def test_opening_failure_rolls_back_book_and_posting(self):
        with patch('finance.services.DemoPosting.objects.create',side_effect=RuntimeError('synthetic posting failure')):
            with self.assertRaises(RuntimeError):self.open()
        self.assertEqual(DemoBook.objects.count(),0)

# SPDX-License-Identifier: MPL-2.0
from unittest import skipUnless
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import connection,DatabaseError,transaction
from django.test import TestCase,override_settings
from django.utils import timezone
from core.models import Dealership,Membership
from customers.models import Customer
from .models import DemoPosting
from .services import open_book,record_receipt


@skipUnless(connection.vendor=='postgresql','Cross-record insert triggers require PostgreSQL')
@override_settings(DEMO_LEDGER_ENABLED=True)
class LedgerDatabaseTests(TestCase):
    def test_direct_insert_cannot_fake_reversal_amount_or_cross_book_link(self):
        dealer=Dealership.objects.create(name='Synthetic trigger dealer')
        user=get_user_model().objects.create_user('ledger-trigger')
        Membership.objects.create(user=user,dealership=dealer,role='owner')
        customer=Customer.objects.create(dealership=dealer,first_name='Riley',last_name='Demo')
        today=timezone.localdate()
        book,_=open_book(dealership_id=dealer.pk,customer_id=customer.pk,actor=user,label='DEMO trigger',source_reference='Synthetic opening',opening_on=today,opening_amount='10.00',request_key=uuid4())
        entry,_=record_receipt(dealership_id=dealer.pk,book_id=book.pk,actor=user,amount='1.00',effective_on=today,reason='Synthetic receipt',request_key=uuid4())
        with self.assertRaises(DatabaseError),transaction.atomic():
            DemoPosting.objects.create(book=book,kind='reversal',amount_cents=200,debit='unapplied',credit='cash_control',reverses=entry,actor=user,reason='Invalid synthetic correction',effective_on=today)
        self.assertEqual(book.postings.count(),2)

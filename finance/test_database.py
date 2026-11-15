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


@override_settings(DEMO_LEDGER_ENABLED=True)
class MigratedLedgerGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealership.objects.create(name='Synthetic database guard dealer')
        cls.foreign_dealer = Dealership.objects.create(name='Foreign database guard dealer')
        cls.owner = get_user_model().objects.create_user('db-guard-owner')
        cls.viewer = get_user_model().objects.create_user('db-guard-viewer')
        cls.foreign = get_user_model().objects.create_user('db-guard-foreign')
        Membership.objects.create(user=cls.owner, dealership=cls.dealer, role='owner')
        Membership.objects.create(user=cls.viewer, dealership=cls.dealer, role='viewer')
        Membership.objects.create(user=cls.foreign, dealership=cls.foreign_dealer, role='owner')
        cls.customer = Customer.objects.create(dealership=cls.dealer, first_name='Synthetic')
        cls.today = timezone.localdate()
        cls.book, _ = open_book(dealership_id=cls.dealer.pk, customer_id=cls.customer.pk, actor=cls.owner,
            label='Synthetic', source_reference='Synthetic', opening_on=cls.today, opening_amount='10', request_key=uuid4())

    def test_direct_book_delete_is_blocked_by_append_only_trigger(self):
        with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('DELETE FROM finance_demobook WHERE id = %s', [self.book.pk])
        self.assertTrue(type(self.book).objects.filter(pk=self.book.pk).exists())

    @skipUnless(connection.vendor == 'postgresql', 'Cross-record insert guards are PostgreSQL-specific')
    def test_database_rejects_foreign_or_read_only_writers_and_invalid_dates(self):
        from datetime import timedelta
        from .models import DemoBook, DemoAccountExport
        bad_book = dict(dealership=self.dealer, customer=self.customer, label='Synthetic',
                        source_reference='Synthetic', opening_on=self.today)
        for actor in (self.viewer, self.foreign):
            with self.subTest(kind='book', actor=actor.pk), self.assertRaises(DatabaseError), transaction.atomic():
                DemoBook.objects.create(created_by=actor, **bad_book)
            with self.subTest(kind='posting', actor=actor.pk), self.assertRaises(DatabaseError), transaction.atomic():
                DemoPosting.objects.create(book=self.book, kind='receipt', amount_cents=100,
                    debit='cash_control', credit='unapplied', actor=actor, reason='Synthetic', effective_on=self.today)
        with self.assertRaises(DatabaseError), transaction.atomic():
            DemoPosting.objects.create(book=self.book, kind='receipt', amount_cents=100,
                debit='cash_control', credit='unapplied', actor=self.owner, reason='Synthetic',
                effective_on=self.today - timedelta(days=1))
        with self.assertRaises(DatabaseError), transaction.atomic():
            DemoAccountExport.objects.create(book=self.book, actor=self.foreign, bundle_sha256='0' * 64,
                bundle_bytes=10, posting_count=1, schedule_count=0)
        # Read-only members may export their own account according to the documented policy.
        DemoAccountExport.objects.create(book=self.book, actor=self.viewer, bundle_sha256='0' * 64,
            bundle_bytes=10, posting_count=1, schedule_count=0)
        self.assertEqual(self.book.postings.count(), 1)

    @skipUnless(connection.vendor == 'postgresql', 'Schedule insert guard is PostgreSQL-specific')
    def test_database_rejects_schedule_result_metadata_mismatch(self):
        from .models import DemoSchedule
        with self.assertRaises(DatabaseError), transaction.atomic():
            DemoSchedule.objects.create(book=self.book, created_by=self.owner, method='precomputed',
                calculation_version='synthetic-v1', inputs={},
                result={'method': 'simple_daily', 'calculation_version': 'synthetic-v1'}, result_sha256='0' * 64)
        self.assertFalse(DemoSchedule.objects.filter(book=self.book).exists())

    def test_database_rejects_context_from_wrong_buyer_or_viewer(self):
        from inventory.models import Vehicle
        from deals.models import DraftDeal
        from .models import DemoAccountContext
        vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='SYN-GUARD', year=2020, make='Synthetic', model='Car')
        another_customer = Customer.objects.create(dealership=self.dealer, first_name='Other synthetic')
        wrong_deal = DraftDeal.objects.create(dealership=self.dealer, buyer=another_customer, vehicle=vehicle, deal_type='bhph')
        correct_deal = DraftDeal.objects.create(dealership=self.dealer, buyer=self.customer, vehicle=vehicle, deal_type='bhph')
        for deal, actor in ((wrong_deal, self.owner), (correct_deal, self.viewer)):
            with self.subTest(deal=deal.pk, actor=actor.pk), self.assertRaises(DatabaseError), transaction.atomic():
                DemoAccountContext.objects.create(book=self.book, deal=deal, created_by=actor, snapshot={}, snapshot_sha256='0' * 64)
        self.assertFalse(DemoAccountContext.objects.filter(book=self.book).exists())

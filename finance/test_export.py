# SPDX-License-Identifier: MPL-2.0
import json
from datetime import date
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from core.models import Membership
from customers.models import Customer
from . import test_account_exports as fixtures
from .export import FORMAT_VERSION, FinanceExportError, export_finance
from .models import (DemoBook, DemoPosting, DemoSchedule, DemoAccountContext,
                     DemoAccountExport, DemoServicingPlan)
from .services import open_book
from .servicing_services import select_baseline


@override_settings(DEBUG=True, DEMO_LEDGER_ENABLED=True, DEMO_SERVICING_ENABLED=True)
class FinanceExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.AccountExportTests.setUpTestData.__func__(cls)
        cls.owner = get_user_model().objects.create_user('finance-export-owner')
        Membership.objects.create(user=cls.owner, dealership=cls.dealer, role='owner')
        cls.plan, _ = select_baseline(dealership_id=cls.dealer.pk, book_id=cls.book.pk,
            schedule_id=cls.schedule.pk, actor=cls.users['staff'], reason='Synthetic baseline',
            creation_key=uuid4(), expected_digest=cls.schedule.result_sha256)
        cls.event = DemoAccountExport.objects.create(book=cls.book, actor=cls.users['staff'],
            format_version='synthetic-old-v1', bundle_sha256='1'*64, bundle_bytes=100,
            posting_count=3, schedule_count=1)
        foreign_customer = Customer.objects.create(dealership=cls.other, first_name='FOREIGN-PRIVATE')
        cls.foreign_book, _ = open_book(dealership_id=cls.other.pk, customer_id=foreign_customer.pk,
            actor=cls.users['foreign'], label='FOREIGN-PRIVATE-BOOK', source_reference='Synthetic',
            opening_on=date(2026,1,1), opening_amount='900', request_key=uuid4())

    def export(self, actor=None, dealership_id=None):
        return export_finance(dealership_id=dealership_id or self.dealer.pk, actor=actor or self.owner)

    def test_complete_scoped_data_and_independent_journal_values(self):
        data = self.export()
        self.assertEqual(data['format'], FORMAT_VERSION)
        self.assertEqual([row['id'] for row in data['books']], [self.book.pk])
        for model, key in ((DemoBook, 'books'), (DemoPosting, 'postings'), (DemoSchedule, 'schedules'),
                           (DemoAccountContext, 'contexts'), (DemoServicingPlan, 'servicing_plans'),
                           (DemoAccountExport, 'export_events')):
            fields = {field.attname for field in model._meta.concrete_fields}
            self.assertTrue(data[key], key)
            self.assertEqual(set(data[key][0]), fields, key)
        postings = {row['kind']: row for row in data['postings']}
        self.assertEqual(postings['opening']['amount_cents'], 100000)
        self.assertEqual(postings['receipt']['amount_cents'], 12550)
        self.assertEqual(postings['reversal']['amount_cents'], 12550)
        self.assertEqual(postings['reversal']['reverses_id'], postings['receipt']['id'])
        self.assertEqual((postings['receipt']['debit'], postings['receipt']['credit']), ('cash_control', 'unapplied'))
        self.assertEqual((postings['reversal']['debit'], postings['reversal']['credit']), ('unapplied', 'cash_control'))
        self.assertEqual(sum(row['amount_cents'] for row in data['postings']), 125100)
        self.assertEqual(data['contexts'][0]['snapshot']['interest_method'], 'Precomputed')
        self.assertEqual(data['schedules'][0]['result'], self.schedule.result)
        self.assertEqual(data['schedules'][0]['calculation_version'], self.schedule.calculation_version)
        self.assertEqual(data['servicing_plans'][0]['policy_version'], self.plan.policy_version)
        self.assertEqual(data['export_events'][0]['format_version'], 'synthetic-old-v1')
        self.assertNotIn('FOREIGN-PRIVATE', json.dumps(data))
        self.assertIn('not guaranteed', data['consistency'])
        self.assertIn('not a complete', data['scope'])

    def test_owner_only_and_synthetic_gates(self):
        for actor in (self.users['staff'], self.users['viewer'], self.users['foreign'], AnonymousUser()):
            with self.subTest(actor=str(actor)), self.assertRaises(PermissionDenied): self.export(actor=actor)
        with self.assertRaises(PermissionDenied): self.export(dealership_id=self.other.pk)
        for setting in ('DEBUG', 'DEMO_LEDGER_ENABLED', 'DEMO_SERVICING_ENABLED'):
            with self.subTest(setting=setting), override_settings(**{setting: False}), self.assertRaises(PermissionDenied): self.export()
        self.owner.is_active = False; self.owner.save(update_fields=['is_active'])
        with self.assertRaises(PermissionDenied): self.export()

    def test_limits_and_integrity_fail_without_partial_results(self):
        for name in ('MAX_BOOKS', 'MAX_CHILD_ROWS', 'MAX_BYTES'):
            with self.subTest(name=name), patch('finance.export.' + name, 0), self.assertRaises(FinanceExportError): self.export()
        with patch('finance.export.result_digest', return_value='tampered'), self.assertRaises(FinanceExportError): self.export()

    def test_cross_dealership_customer_reference_rejected(self):
        self.customer.dealership = self.other
        self.customer.save(update_fields=['dealership'])
        with self.assertRaises(FinanceExportError): self.export()

    def test_original_frozen_context_is_not_rebuilt_from_profiles(self):
        before = self.export()['contexts'][0]
        self.customer.first_name = 'Changed'; self.customer.save()
        self.vehicle.model = 'Changed'; self.vehicle.save()
        self.assertEqual(self.export()['contexts'][0], before)

    def test_corrupt_reversal_and_incomplete_capture_are_rejected(self):
        from copy import copy
        from .export import _verify_journal
        opening = self.book.postings.get(kind='opening')
        reversal = self.book.postings.get(kind='reversal')
        invalid = copy(reversal)
        invalid.amount_cents += 1
        with self.assertRaises(FinanceExportError):
            _verify_journal([self.book], [opening, self.receipt, invalid])
        invalid = copy(reversal)
        invalid.reverses_id = self.foreign_book.postings.get(kind='opening').pk
        with self.assertRaises(FinanceExportError):
            _verify_journal([self.book], [opening, self.receipt, invalid])
        with self.assertRaises(FinanceExportError):
            _verify_journal([self.book], [self.receipt, reversal])

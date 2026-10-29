# SPDX-License-Identifier: MPL-2.0
import csv,hashlib,io,json,zipfile
from datetime import date
from uuid import uuid4
from unittest.mock import patch
from django.db import DatabaseError,transaction
from django.test import TestCase,override_settings
from django.urls import reverse
from deals.account_context import account_draft_snapshot
from . import test_accounts as fixtures
from .models import DemoAccountExport,DemoPosting
from .account_services import link_draft
from .schedule_services import result_digest,calculate_for_book,save_illustration
from .services import record_receipt,reverse_receipt


@override_settings(DEMO_LEDGER_ENABLED=True)
class AccountExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.AccountWorkspaceTests.setUpTestData.__func__(cls)
        link_draft(dealership_id=cls.dealer.pk,book_id=cls.book.pk,deal_id=cls.deal.pk,actor=cls.users['staff'],expected_digest=result_digest(account_draft_snapshot(cls.deal)))
        cls.receipt,_=record_receipt(dealership_id=cls.dealer.pk,book_id=cls.book.pk,actor=cls.users['staff'],amount='125.50',effective_on=date(2026,2,1),reason='=Synthetic formula-like reference',request_key=uuid4())
        reverse_receipt(dealership_id=cls.dealer.pk,book_id=cls.book.pk,posting_id=cls.receipt.pk,actor=cls.users['staff'],effective_on=date(2026,2,2),reason='Synthetic correction',request_key=uuid4())
        inputs={'method':'precomputed','first_due_on':'2026-02-01','count':3,'frequency':'monthly','first_day':None,'second_day':None,'finance_charge':'100','contract_rate':None,'regular_payment':None}
        result=calculate_for_book(cls.book,inputs)
        cls.schedule,_=save_illustration(dealership_id=cls.dealer.pk,book_id=cls.book.pk,actor=cls.users['staff'],inputs=inputs,expected_digest=result_digest(result),creation_key=uuid4())

    def setUp(self):
        self.client.force_login(self.users['staff'])
        self.url=reverse('account_export_download',args=[self.book.pk])
        self.review=reverse('account_export_review',args=[self.book.pk])

    def archive(self,response):
        self.assertEqual(response.status_code,200)
        return zipfile.ZipFile(io.BytesIO(response.content))

    def test_complete_bundle_exact_values_hashes_and_reversal_links(self):
        response=self.client.get(self.url)
        with self.archive(response) as archive:
            self.assertEqual(set(archive.namelist()),{'account.json','journal.json','journal.csv','schedules.json','README.txt','manifest.json'})
            manifest=json.loads(archive.read('manifest.json'))
            for name,metadata in manifest['files'].items():
                data=archive.read(name);self.assertEqual(len(data),metadata['bytes']);self.assertEqual(hashlib.sha256(data).hexdigest(),metadata['sha256'])
            account=json.loads(archive.read('account.json'))
            journal=json.loads(archive.read('journal.json'))
            schedules=json.loads(archive.read('schedules.json'))
            self.assertEqual(account['reconciliation']['net_debit']['principal'],100000)
            self.assertEqual(account['reconciliation']['net_debit']['unapplied'],0)
            self.assertEqual(account['reconciliation']['total_debits_cents'],125100)
            self.assertEqual(len(journal),3)
            self.assertEqual(journal[-1]['reverses_id'],self.receipt.pk)
            self.assertEqual(journal[1]['amount_cents'],12550)
            self.assertEqual(journal[1]['amount_usd'],'125.50')
            self.assertEqual(account['linked_context']['snapshot']['interest_method'],'Precomputed')
            self.assertEqual(schedules[0]['result']['rows'][-1]['payment_cents'],36666)
            self.assertIn('not encrypted',archive.read('README.txt').decode())
        event=DemoAccountExport.objects.get()
        self.assertEqual(event.bundle_sha256,hashlib.sha256(response.content).hexdigest())
        self.assertEqual((event.posting_count,event.schedule_count),(3,1))
        self.assertEqual(event.bundle_bytes,len(response.content))
        self.assertIn('no-store',response['Cache-Control'])
        self.assertIn('attachment',response['Content-Disposition'])

    def test_csv_neutralizes_formula_text_but_json_retains_exact_reference(self):
        with self.archive(self.client.get(self.url)) as archive:
            rows=list(csv.DictReader(io.StringIO(archive.read('journal.csv').decode('utf-8-sig'))))
            self.assertEqual(rows[1]['reason'],"'=Synthetic formula-like reference")
            raw=json.loads(archive.read('journal.json'))
            self.assertEqual(raw[1]['reason'],'=Synthetic formula-like reference')

    def test_export_uses_retained_illustrations_and_linked_facts(self):
        self.proposal.interest_method='simple';self.proposal.save()
        with patch('finance.schedules.calculate',side_effect=AssertionError('Do not recalculate')):
            with self.archive(self.client.get(self.url)) as archive:
                self.assertEqual(json.loads(archive.read('account.json'))['linked_context']['snapshot']['interest_method'],'Precomputed')
                self.assertEqual(json.loads(archive.read('schedules.json'))[0]['result'],self.schedule.result)
        self.assertEqual(DemoPosting.objects.count(),3)

    def test_review_and_head_do_not_generate_export_events(self):
        self.assertContains(self.client.get(self.review),'Download demo account ZIP')
        response=self.client.head(self.url)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content,b'')
        self.assertFalse(DemoAccountExport.objects.exists())
        self.client.get(self.url)
        self.assertContains(self.client.get(self.review),'Recent exports prepared')
        self.assertEqual(DemoAccountExport.objects.count(),1)

    def test_readers_can_export_only_their_dealership_and_disabled_gate_closes(self):
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.assertEqual(self.client.get(self.review).status_code,404)
        self.assertEqual(self.client.post(self.url).status_code,405)
        self.client.force_login(self.users['staff'])
        with override_settings(DEMO_LEDGER_ENABLED=False):
            self.assertEqual(self.client.get(self.url).status_code,403)
        self.assertEqual(DemoAccountExport.objects.count(),1)

    def test_integrity_failure_and_oversize_never_return_partial_zip_or_audit(self):
        with patch('finance.account_exports.result_digest',return_value='bad'):
            self.assertEqual(self.client.get(self.url).status_code,409)
        with patch('finance.account_exports.MAX_BYTES',1):
            self.assertEqual(self.client.get(self.url).status_code,409)
        with patch('finance.account_exports.reconcile',return_value={'balanced':False}):
            self.assertEqual(self.client.get(self.url).status_code,409)
        self.assertFalse(DemoAccountExport.objects.exists())

    def test_failed_audit_does_not_return_an_untracked_export(self):
        with patch('finance.account_exports.DemoAccountExport.objects.create',side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError):self.client.get(self.url)
        self.assertFalse(DemoAccountExport.objects.exists())
        self.assertEqual(DemoPosting.objects.count(),3)

    def test_audit_update_and_delete_blocked(self):
        self.client.get(self.url)
        for action in ('update','delete'):
            with self.assertRaises(DatabaseError),transaction.atomic():
                qs=DemoAccountExport.objects.all()
                qs.update(bundle_sha256='changed') if action=='update' else qs.delete()

    def test_exports_include_entries_beyond_workspace_pagination(self):
        for number in range(25):
            record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.users['staff'],amount='1',effective_on=date(2026,2,3),reason=f'Synthetic export row {number}',request_key=uuid4())
        with self.archive(self.client.get(self.url)) as archive:
            self.assertEqual(len(json.loads(archive.read('journal.json'))),28)
            self.assertEqual(json.loads(archive.read('account.json'))['reconciliation']['net_debit']['unapplied'],-2500)

    def test_versioned_export_includes_current_structured_contact_address(self):
        self.customer.address_line1='123 Synthetic Export Lane';self.customer.city='Demo City';self.customer.save()
        with self.archive(self.client.get(self.url)) as archive:
            record=json.loads(archive.read('account.json'))
            self.assertEqual(record['format'],'demo-account-export-v4')
            self.assertEqual(record['current_customer']['address']['address_line1'],'123 Synthetic Export Lane')
            self.assertEqual(record['current_customer']['address']['city'],'Demo City')

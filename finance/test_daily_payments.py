# SPDX-License-Identifier: MPL-2.0
from datetime import date,datetime,timezone as dt_timezone
from uuid import uuid4
from unittest.mock import patch
from django.db import DatabaseError,transaction
from django.test import TestCase,override_settings
from django.urls import reverse
from . import test_accounts as fixtures
from .models import DemoPosting
from .services import LedgerError,record_receipt,reverse_receipt
from .payment_register import capture


@override_settings(DEMO_LEDGER_ENABLED=True)
class DailyPaymentsTests(TestCase):
    @classmethod
    def setUpTestData(cls):fixtures.AccountWorkspaceTests.setUpTestData.__func__(cls)
    def setUp(self):
        self.client.force_login(self.users['staff']);self.url=reverse('payment_register')
    def receipt(self,amount,method='unspecified',day=10,request_key=None):
        with patch('django.utils.timezone.now',return_value=datetime(2026,3,day,16,tzinfo=dt_timezone.utc)):
            return record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.users['staff'],amount=amount,effective_on=date(2026,3,day),reason='Invented daily payment',request_key=request_key or uuid4(),payment_method=method)[0]
    def reverse(self,posting,day=10):
        with patch('django.utils.timezone.now',return_value=datetime(2026,3,day,17,tzinfo=dt_timezone.utc)):
            return reverse_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,posting_id=posting.pk,actor=self.users['staff'],effective_on=date(2026,3,day),reason='Invented daily reversal',request_key=uuid4())[0]
    def test_independent_method_totals_tie_to_same_capture(self):
        cash=self.receipt('100.25','cash');self.receipt('200','check');self.receipt('30.50','other');self.receipt('7.75');self.reverse(cash)
        with self.assertNumQueries(1):
            entries,totals=capture(dealership_id=self.dealer.pk,start=date(2026,3,10),end=date(2026,3,10),basis='recorded')
        self.assertEqual(len(entries),5)
        self.assertEqual((totals['receipts_cents'],totals['corrections_cents'],totals['net_cents']),(33850,10025,23825))
        methods={r['method']:r for r in totals['methods']}
        self.assertEqual((methods['cash']['receipts_cents'],methods['cash']['reversals_cents'],methods['cash']['net_cents']),(10025,10025,0))
        self.assertEqual(methods['check']['net'],'$200.00');self.assertEqual(methods['other']['net'],'$30.50');self.assertEqual(methods['unspecified']['net'],'$7.75')
        self.assertEqual(sum(r['net_cents'] for r in totals['methods']),23825)

    def test_reversal_follows_original_method_on_a_later_day(self):
        receipt=self.receipt('88.25','check');correction=self.reverse(receipt,day=11)
        self.assertEqual(correction.payment_method,'check')
        response=self.client.get(self.url,{'basis':'recorded','start':'2026-03-11','end':'2026-03-11'})
        self.assertEqual(response.context['net'],'-$88.25')
        methods={r['method']:r for r in response.context['totals']['methods']}
        self.assertEqual(methods['check']['net_cents'],-8825);self.assertEqual(methods['cash']['net_cents'],0)
        self.assertContains(response,reverse('bhph_account_receipt',args=[self.book.pk,receipt.pk])+'#reversal')

    def test_method_retry_mismatch_invalid_choice_and_immutable_posting(self):
        key=uuid4();receipt=self.receipt('10','cash',request_key=key)
        self.assertEqual(self.receipt('10','cash',request_key=key).pk,receipt.pk)
        with self.assertRaises(LedgerError):self.receipt('10','check',request_key=key)
        with self.assertRaises(LedgerError):self.receipt('10','invalid')
        with self.assertRaises(DatabaseError),transaction.atomic():DemoPosting.objects.filter(pk=receipt.pk).update(payment_method='check')
        self.assertEqual(self.book.postings.filter(kind='receipt').count(),1)

    def test_database_rejects_wrong_reversal_method_and_invalid_insert(self):
        original=self.receipt('10','cash')
        data={'book':self.book,'actor':self.users['staff'],'effective_on':date(2026,3,10),'reason':'Invented invalid method','amount_cents':1000}
        with self.assertRaises(DatabaseError),transaction.atomic():
            DemoPosting.objects.create(**data,kind='reversal',reverses=original,debit='unapplied',credit='cash_control',payment_method='check')
        with self.assertRaises(DatabaseError),transaction.atomic():
            DemoPosting.objects.create(**data,kind='receipt',debit='cash_control',credit='unapplied',payment_method='invalid')
        self.assertEqual(self.book.postings.count(),2)

    def test_receipt_preview_edit_confirm_carries_method_without_changing_reversal_form(self):
        data={'amount':'12.34','payment_method':'check','effective_on':'2026-03-10','reference':'Invented check note','request_key':str(uuid4()),'synthetic_confirmed':'on'}
        url=reverse('ledger_demo_receipt',args=[self.book.pk]);response=self.client.post(url,data)
        self.assertContains(response,'Check');token=response.context['token']
        edited=self.client.post(reverse('ledger_demo_confirm'),{'preview_token':token,'action':'edit'})
        self.assertEqual(edited.context['form']['payment_method'].value(),'check')
        saved=self.client.post(reverse('ledger_demo_confirm'),{'preview_token':token,'action':'post'})
        receipt=self.book.postings.get(kind='receipt');self.assertEqual(receipt.payment_method,'check')
        self.assertContains(self.client.get(saved.url),'Check')
        self.assertEqual(self.client.post(url,data).url,saved.url)
        self.assertEqual(self.client.post(url,{**data,'payment_method':'cash'}).status_code,409)
        form=self.client.get(reverse('ledger_demo_reverse',args=[self.book.pk,receipt.pk])).context['form']
        self.assertNotIn('payment_method',form.fields)

    def test_daily_default_empty_and_date_navigation_do_not_write(self):
        before=list(self.book.postings.values())
        with patch('finance.payment_register.timezone.localdate',return_value=date(2026,3,10)):
            response=self.client.get(self.url)
        self.assertEqual(response.context['selected_day'],date(2026,3,10));self.assertEqual(response.context['net'],'$0.00')
        self.assertContains(response,'No receipts or reversals');self.assertContains(response,'Previous day');self.assertNotContains(response,'Next day')
        self.assertEqual(list(self.book.postings.values()),before)
        response=self.client.get(self.url,{'start':'2026-03-10','end':'2026-03-10'})
        self.assertContains(response,'Next day');self.assertFalse(response.context['custom_range'])
        self.assertContains(self.client.get(reverse('ledger_demo_list')),'Daily payments')

    def test_export_v4_preserves_method_for_receipt_and_reversal(self):
        import io,json,zipfile
        receipt=self.receipt('12.34','other');self.reverse(receipt)
        response=self.client.get(reverse('account_export_download',args=[self.book.pk]))
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            journal=json.loads(archive.read('journal.json'))
            self.assertEqual({p['kind']:p['payment_method'] for p in journal},{'opening':'unspecified','receipt':'other','reversal':'other'})
            self.assertEqual(json.loads(archive.read('account.json'))['format'],'demo-account-export-v4')
            self.assertIn('payment_method',archive.read('journal.csv').decode())

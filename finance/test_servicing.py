# SPDX-License-Identifier: MPL-2.0
from datetime import date,datetime,timezone as dt_timezone
from uuid import uuid4
from django.test import SimpleTestCase,TestCase,override_settings,Client
from django.db import DatabaseError,transaction
from django.urls import reverse
from .servicing import project,POLICY
from .services import LedgerError,record_receipt,reverse_receipt,reconcile
from .schedule_services import calculate_for_book,result_digest,save_illustration
from .servicing_services import select_baseline,projection_for_book
from .models import DemoServicingPlan
from . import test_accounts as fixtures

UTC=dt_timezone.utc
CAPTURE=datetime(2026,5,1,tzinfo=UTC)
ROWS=[{'number':1,'due_on':'2026-02-01','payment_cents':10000},
      {'number':2,'due_on':'2026-03-01','payment_cents':10000},
      {'number':3,'due_on':'2026-04-01','payment_cents':10000}]

def receipt(amount,*,pk=1,effective=date(2026,1,31),entered=datetime(2026,2,1,tzinfo=UTC)):
    return {'id':pk,'kind':'receipt','amount_cents':amount,'effective_on':effective,'entered_at':entered,'reverses_id':None}

def correction(amount,*,effective=date(2026,3,3),entered=datetime(2026,3,3,tzinfo=UTC)):
    return {**receipt(amount,pk=2,effective=effective,entered=entered),'kind':'reversal','reverses_id':1}

class ServicingReferenceTests(SimpleTestCase):
    def calc(self,postings=(),as_of=date(2026,3,2),**kw):
        return project(rows=ROWS,postings=list(postings),as_of=as_of,recorded_through=kw.get('recorded_through',CAPTURE))

    def test_missed_partial_extra_and_excess_independent_cases(self):
        for paid,due,days,remaining,excess,status in [
            (0,20000,29,30000,0,'past_due'),(4000,16000,29,26000,0,'past_due'),
            (15000,5000,1,15000,0,'past_due'),(25000,0,0,5000,0,'current'),
            (32500,0,0,0,2500,'covered')]:
            with self.subTest(paid=paid):
                r=self.calc([receipt(paid)] if paid else [])
                self.assertEqual((r['amount_due_cents'],r['days_past_due'],r['remaining_scheduled_cents'],r['excess_cents'],r['status']),(due,days,remaining,excess,status))
                self.assertEqual(r['covered_cents']+r['excess_cents'],paid)
                self.assertEqual(r['covered_cents']+r['remaining_scheduled_cents'],30000)

    def test_due_today_is_not_late_and_before_due_is_current(self):
        r=self.calc(as_of=date(2026,2,1))
        self.assertEqual((r['amount_due_cents'],r['past_due_cents'],r['days_past_due'],r['status']),(10000,0,0,'due_today'))
        self.assertEqual(self.calc(as_of=date(2026,1,31))['status'],'current')

    def test_partial_coverage_has_traceable_receipt_installment_links(self):
        r=self.calc([receipt(15000)])
        self.assertEqual(r['coverage'],[{'receipt_id':1,'installment':1,'coverage_cents':10000},{'receipt_id':1,'installment':2,'coverage_cents':5000}])
        self.assertEqual(r['next_unpaid_on'],'2026-03-01')

    def test_reversals_respect_effective_date_and_record_capture(self):
        events=[receipt(15000),correction(15000)]
        self.assertEqual(self.calc(events)['amount_due_cents'],5000)
        self.assertEqual(self.calc(events,as_of=date(2026,3,4))['amount_due_cents'],20000)
        self.assertEqual(self.calc(events,as_of=date(2026,3,4),recorded_through=datetime(2026,3,2,tzinfo=UTC))['amount_due_cents'],5000)
        self.assertEqual(self.calc([receipt(15000,effective=date(2026,3,3))])['amount_due_cents'],20000)

    def test_final_cent_and_coverage_conservation(self):
        rows=[{**row,'payment_cents':cents} for row,cents in zip(ROWS,[36667,36667,36666])]
        r=project(rows=rows,postings=[receipt(110000)],as_of=date(2026,4,1),recorded_through=CAPTURE)
        self.assertEqual([row['covered_cents'] for row in r['rows']],[36667,36667,36666])
        self.assertEqual((r['amount_due_cents'],r['remaining_scheduled_cents'],r['excess_cents']),(0,0,0))

    def test_invalid_inputs_fail_instead_of_returning_green(self):
        for events in ([receipt(True)],[receipt(10000),correction(9999)],[correction(10000)],[receipt(10000),receipt(10000)]):
            with self.subTest(events=events),self.assertRaises(LedgerError):self.calc(events)
        with self.assertRaises(LedgerError):project(rows=[],postings=[],as_of=date(2026,3,2),recorded_through=CAPTURE)


@override_settings(DEMO_LEDGER_ENABLED=True,DEMO_SERVICING_ENABLED=True)
class ServicingIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.AccountWorkspaceTests.setUpTestData.__func__(cls)
        cls.inputs={'method':'precomputed','frequency':'monthly','first_due_on':'2026-02-01','count':10,'first_day':None,'second_day':None,'finance_charge':'0.00','contract_rate':None,'regular_payment':None}
        result=calculate_for_book(cls.book,cls.inputs)
        cls.schedule,_=save_illustration(dealership_id=cls.dealer.pk,book_id=cls.book.pk,actor=cls.users['staff'],inputs=cls.inputs,expected_digest=result_digest(result),creation_key=uuid4())

    def setUp(self):self.client.force_login(self.users['staff'])
    def choose(self,**kw):
        args=dict(dealership_id=self.dealer.pk,book_id=self.book.pk,schedule_id=self.schedule.pk,actor=self.users['staff'],reason='Invented baseline reference',creation_key=uuid4(),expected_digest=self.schedule.result_sha256);args.update(kw)
        return select_baseline(**args)

    def test_selection_retry_immutable_and_no_money_changes(self):
        before=list(self.book.postings.values());request_key=uuid4()
        first,created=self.choose(creation_key=request_key);again,repeated=self.choose(creation_key=request_key)
        self.assertTrue(created);self.assertFalse(repeated);self.assertEqual(first.pk,again.pk)
        with self.assertRaises(LedgerError):self.choose()
        self.assertEqual(list(self.book.postings.values()),before)
        with self.assertRaises(DatabaseError),transaction.atomic():DemoServicingPlan.objects.filter(pk=first.pk).update(reason='replace')
        with self.assertRaises(DatabaseError),transaction.atomic():DemoServicingPlan.objects.filter(pk=first.pk).delete()

    def test_projection_leaves_posted_principal_and_funds_unapplied(self):
        self.choose()
        p,_=record_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.users['staff'],amount='150',effective_on=date(2026,2,1),reason='Invented partial and extra coverage',request_key=uuid4())
        before=reconcile(dealership_id=self.dealer.pk,book_id=self.book.pk)
        r=projection_for_book(self.book,as_of=date(2026,3,2))
        self.assertEqual(r['amount_due_cents'],5000)
        self.assertEqual(r['status'],'past_due')
        self.assertEqual(before,reconcile(dealership_id=self.dealer.pk,book_id=self.book.pk))
        self.assertEqual(before['net_debit']['principal'],100000)
        self.assertEqual(before['net_debit']['unapplied'],-15000)
        reverse_receipt(dealership_id=self.dealer.pk,book_id=self.book.pk,posting_id=p.pk,actor=self.users['staff'],effective_on=date(2026,3,3),reason='Invented correction',request_key=uuid4())
        self.assertEqual(projection_for_book(self.book,as_of=date(2026,3,2))['amount_due_cents'],5000)
        self.assertEqual(projection_for_book(self.book,as_of=date(2026,3,4))['amount_due_cents'],20000)

    def test_preview_edit_confirm_and_contextual_status(self):
        url=reverse('servicing_setup',args=[self.book.pk])
        data={'schedule':self.schedule.pk,'reason':'Synthetic choice','creation_key':uuid4(),'synthetic_confirmed':'on'}
        preview=self.client.post(url,data)
        self.assertFalse(DemoServicingPlan.objects.exists());token=preview.context['token']
        edited=self.client.post(url,{'preview_token':token,'action':'edit'})
        self.assertContains(edited,f'action="{url}"')
        self.assertEqual(edited.context['form']['reason'].value(),'Synthetic choice')
        first=self.client.post(url,{'preview_token':token,'action':'choose'})
        self.assertEqual(first.status_code,302)
        self.assertEqual(self.client.post(url,{'preview_token':token,'action':'choose'}).url,first.url)
        detail=self.client.get(first.url,{'as_of':'2026-03-02'})
        self.assertContains(detail,'Demo past due');self.assertContains(detail,'$200.00')
        self.assertContains(self.client.get(reverse('bhph_account',args=[self.book.pk])),'demo')
        self.assertEqual(self.client.get(first.url,{'as_of':'2100-01-01'}).status_code,400)
        self.assertEqual(self.client.get(first.url,{'as_of':'invalid'}).status_code,400)

    def test_permissions_gate_and_tampered_selection(self):
        url=reverse('servicing_setup',args=[self.book.pk])
        self.assertEqual(self.client.post(url,{'preview_token':'bad','action':'choose'}).status_code,400)
        self.client.force_login(self.users['viewer']);self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.users['foreign']);self.assertEqual(self.client.get(url).status_code,404)
        self.client.force_login(self.users['staff'])
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.users['staff']);self.assertEqual(strict.post(url,{}).status_code,403)
        with override_settings(DEMO_SERVICING_ENABLED=False):self.assertEqual(self.client.get(url).status_code,403)

    def test_foreign_digest_and_non_monthly_baselines_are_rejected(self):
        with self.assertRaises(LedgerError):self.choose(expected_digest='0'*64)
        weekly={**self.inputs,'frequency':'weekly'};result=calculate_for_book(self.book,weekly)
        schedule,_=save_illustration(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.users['staff'],inputs=weekly,expected_digest=result_digest(result),creation_key=uuid4())
        with self.assertRaises(LedgerError):self.choose(schedule_id=schedule.pk,expected_digest=schedule.result_sha256)

    def test_export_preserves_selected_baseline(self):
        import io,json,zipfile
        plan,_=self.choose()
        response=self.client.get(reverse('account_export_download',args=[self.book.pk]))
        with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
            facts=json.loads(bundle.read('account.json'))
            self.assertEqual(facts['servicing_simulation']['id'],plan.pk)
            self.assertEqual(facts['servicing_simulation']['policy_version'],POLICY)
            self.assertEqual(facts['servicing_simulation']['schedule_sha256'],self.schedule.result_sha256)

    def test_list_shows_demo_status_and_unselected_accounts_stay_neutral(self):
        self.choose()
        response=self.client.get(reverse('ledger_demo_list'))
        self.assertContains(response,'Demo past due')
        self.assertContains(response,'simulation-past_due')
        self.assertEqual(next(b for b in response.context['page'] if b.pk==self.book.pk).simulation['status'],'past_due')
        with override_settings(DEMO_SERVICING_ENABLED=False):
            self.assertNotContains(self.client.get(reverse('ledger_demo_list')),'Demo due / status')

    def test_database_rejects_non_monthly_direct_baseline_insert(self):
        weekly={**self.inputs,'frequency':'weekly'};result=calculate_for_book(self.book,weekly)
        schedule,_=save_illustration(dealership_id=self.dealer.pk,book_id=self.book.pk,actor=self.users['staff'],inputs=weekly,expected_digest=result_digest(result),creation_key=uuid4())
        with self.assertRaises(DatabaseError),transaction.atomic():
            DemoServicingPlan.objects.create(book=self.book,schedule=schedule,schedule_sha256=schedule.result_sha256,reason='Invalid direct insert',created_by=self.users['staff'])

# SPDX-License-Identifier: MPL-2.0
from datetime import date,timedelta
from django.test import SimpleTestCase
from .services import LedgerError
from .schedules import calculate,due_dates


class ScheduleArithmeticTests(SimpleTestCase):
    def base(self,**kwargs):
        args=dict(principal_cents=100000,method='precomputed',start_on=date(2026,1,1),first_due_on=date(2026,2,1),count=3,frequency='monthly',finance_charge='100.00');args.update(kwargs);return calculate(**args)

    def test_independent_precomputed_reference_and_final_cent_residual(self):
        result=self.base()
        self.assertEqual([row['payment_cents'] for row in result['rows']],[36667,36667,36666])
        self.assertEqual([row['remaining_scheduled_cents'] for row in result['rows']],[73333,36666,0])
        self.assertEqual(result['total_payments_cents'],110000)
        self.assertNotIn('interest_cents',result['rows'][0])
        self.assertNotIn('remaining_principal_cents',result['rows'][0])

    def test_independent_daily_simple_reference(self):
        result=self.base(method='simple_daily',start_on=date(2026,1,1),first_due_on=date(2026,1,11),count=2,frequency='semimonthly',first_day=11,second_day=21,finance_charge=None,contract_rate='36.5',regular_payment='510.00')
        # Ten-day second interval at $500 principal => $5.00; final $505.00.
        self.assertEqual([row['interest_cents'] for row in result['rows']],[1000,500])
        self.assertEqual([row['principal_cents'] for row in result['rows']],[50000,50000])
        self.assertEqual([row['payment_cents'] for row in result['rows']],[51000,50500])
        self.assertEqual(result['finance_charge_cents'],1500)
        self.assertEqual(result['total_payments_cents'],101500)

    def test_zero_rate_and_total_principal_conservation(self):
        result=self.base(method='simple_daily',finance_charge=None,contract_rate='0',regular_payment='100.00',count=10)
        self.assertEqual(result['finance_charge_cents'],0)
        self.assertEqual(sum(row['principal_cents'] for row in result['rows']),100000)
        self.assertEqual(result['rows'][-1]['remaining_principal_cents'],0)
        self.assertEqual(result['total_payments_cents'],100000)

    def test_monthly_original_anchor_does_not_drift(self):
        for year,febday in ((2026,28),(2028,29)):
            result=due_dates(start_on=date(year,1,1),first_due_on=date(year,1,31),count=3,frequency='monthly')
            self.assertEqual(result,[date(year,1,31),date(year,2,febday),date(year,3,31)])

    def test_twice_monthly_and_biweekly_are_distinct(self):
        twice=due_dates(start_on=date(2026,1,1),first_due_on=date(2026,1,5),count=4,frequency='semimonthly',first_day=5,second_day=20)
        every_two=due_dates(start_on=date(2026,1,1),first_due_on=date(2026,1,5),count=4,frequency='biweekly')
        self.assertEqual(twice,[date(2026,1,5),date(2026,1,20),date(2026,2,5),date(2026,2,20)])
        self.assertEqual(every_two,[date(2026,1,5),date(2026,1,19),date(2026,2,2),date(2026,2,16)])

    def test_invalid_anchors_counts_dates_and_frequency(self):
        for kwargs in ({'count':0},{'count':601},{'count':True},{'frequency':'unknown'},{'first_due_on':date(2026,1,1)},{'first_day':5},{'frequency':'semimonthly','first_day':20,'second_day':5},{'first_due_on':date(2100,12,31)}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(LedgerError):self.base(**kwargs)

    def test_mixed_method_fields_and_unreviewed_auto_conversions_rejected(self):
        for kwargs in ({'contract_rate':'12'},{'regular_payment':'100'},{'finance_charge':None},{'method':'unknown'}):
            with self.assertRaises(LedgerError):self.base(**kwargs)

    def test_simple_negative_amortization_balloon_and_early_clearance_rejected(self):
        for payment,count in (('0.01',3),('1.00',3),('10000.00',3)):
            with self.subTest(payment=payment):
                with self.assertRaises(LedgerError):self.base(method='simple_daily',finance_charge=None,contract_rate='12',regular_payment=payment,count=count)

    def test_half_cent_interest_rounding_and_fixed365_leap_assumption(self):
        result=self.base(principal_cents=100,method='simple_daily',start_on=date(2028,2,28),first_due_on=date(2028,2,29),count=1,finance_charge=None,contract_rate='182.5',regular_payment='1.01')
        self.assertEqual(result['rows'][0]['days'],1)
        self.assertEqual(result['rows'][0]['interest_cents'],1)
        self.assertEqual(result['day_basis'],365)

    def test_zero_finance_charge_supported_and_fractional_cents_rejected(self):
        self.assertEqual(self.base(finance_charge='0.00')['finance_charge_cents'],0)
        for charge in ('1.001','NaN',False,1.5):
            with self.assertRaises(LedgerError):self.base(finance_charge=charge)

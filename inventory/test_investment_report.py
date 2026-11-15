# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import Dealership, Membership
from .models import Vehicle
from .reconditioning import add_cost, reverse_cost


@override_settings(RECON_DEMO_ENABLED=True)
class InvestmentReportTests(TestCase):
    def setUp(self):
        self.dealer=Dealership.objects.create(name='Synthetic report')
        self.other=Dealership.objects.create(name='Other report')
        self.user=get_user_model().objects.create_user('report-staff')
        Membership.objects.create(user=self.user,dealership=self.dealer,role='staff')
        self.vehicle=Vehicle.objects.create(dealership=self.dealer,stock_number='RPT-1',year=2020,make='Synthetic',model='Report Sedan',acquisition_cost=Decimal('5000.10'),recon_cost=Decimal('100.20'),asking_price=Decimal('6000'))
        Vehicle.objects.create(dealership=self.other,stock_number='PRIVATE-REPORT',year=2020,make='Private',model='Report')
        self.client.force_login(self.user)

    def test_cost_reversal_scope_and_unknown_age(self):
        entry=add_cost(vehicle_id=self.vehicle.pk,dealership=self.dealer,actor=self.user,data={'amount':Decimal('250.35'),'category':'repair','description':'Practice repair','effective_on':timezone.localdate(),'request_key':uuid4()})
        response=self.client.get(reverse('inventory_investment_report'))
        self.assertContains(response,'5,350.65');self.assertContains(response,'649.35')
        self.assertContains(response,'Date not entered');self.assertNotContains(response,'PRIVATE-REPORT')
        self.assertContains(response,reverse('vehicle_recon',args=[self.vehicle.pk]))
        self.assertContains(response,'investment-report-table')
        self.assertIn('no-store',response['Cache-Control'])
        self.assertEqual(self.client.get(reverse('inventory_investment_report'),{'status':'acquired'}).context['page_obj'].paginator.count,1)
        reverse_cost(vehicle_id=self.vehicle.pk,dealership=self.dealer,actor=self.user,entry_id=entry.pk,reason='Practice correction',request_key=uuid4())
        response=self.client.get(reverse('inventory_investment_report'))
        self.assertContains(response,'5,100.30');self.assertContains(response,'899.70')

    def test_sold_filter_and_demo_gate(self):
        self.vehicle.status='sold';self.vehicle.save()
        url=reverse('inventory_investment_report')
        self.assertEqual(self.client.get(url).context['page_obj'].paginator.count,0)
        self.assertEqual(self.client.get(url,{'status':'sold'}).context['page_obj'].paginator.count,1)
        with override_settings(RECON_DEMO_ENABLED=False):self.assertEqual(self.client.get(url).status_code,404)

    def test_filtered_totals_cover_all_pages_and_sort_before_pagination(self):
        for n in range(30):
            Vehicle.objects.create(dealership=self.dealer,stock_number=f'MATCH-{n:02d}',year=2020,make='Searchable',model='Car',acquisition_cost=Decimal('100.25'),asking_price=Decimal('200') if n < 20 else None)
        Vehicle.objects.create(dealership=self.other,stock_number='MATCH-PRIVATE',year=2020,make='Searchable',model='Private',acquisition_cost=99999)
        url=reverse('inventory_investment_report')
        response=self.client.get(url,{'q':'Searchable','sort':'cost_high'})
        self.assertEqual(response.context['summary']['count'],30)
        self.assertEqual(response.context['summary']['cost'],Decimal('3007.50'))
        self.assertEqual(response.context['summary']['priced_count'],20)
        self.assertEqual(response.context['summary']['asking'],Decimal('4000'))
        self.assertEqual(len(response.context['vehicles']),25)
        second=self.client.get(url,{'q':'Searchable','sort':'cost_high','page':2})
        self.assertEqual(second.context['summary']['cost'],Decimal('3007.50'))
        self.assertEqual(len(second.context['vehicles']),5)
        self.assertIn('q=Searchable',second.context['pagination_query'])
        self.assertNotContains(response,'MATCH-PRIVATE')

    def test_age_buckets_and_unknown_with_filter_and_pagination(self):
        from datetime import timedelta
        today=timezone.localdate()
        dates=[(0,'0_30'),(30,'0_30'),(31,'31_60'),(60,'31_60'),(61,'61_90'),(90,'61_90'),(91,'over_90')]
        for days,bucket in dates:
            Vehicle.objects.create(dealership=self.dealer,stock_number=f'AGE-{days}',year=2020,make='Synthetic',model='Aging',acquired_on=today-timedelta(days=days))
        Vehicle.objects.create(dealership=self.dealer,stock_number='FUTURE',year=2020,make='Synthetic',model='Future',acquired_on=today+timedelta(days=1))
        url=reverse('inventory_investment_report')
        for bucket,count in [('0_30',2),('31_60',2),('61_90',2),('over_90',1),('unknown',2)]:
            response=self.client.get(url,{'age':bucket})
            self.assertEqual(response.context['summary']['count'],count)
            self.assertIn('age='+bucket,response.context['pagination_query'])
        self.assertContains(self.client.get(url,{'age':'unknown'}),'Future date · review')

    def test_date_validation_and_legacy_form_preserves_date(self):
        from datetime import timedelta
        self.vehicle.acquired_on=timezone.localdate()-timedelta(days=45);self.vehicle.save()
        data={'stock_number':self.vehicle.stock_number,'year':2020,'make':'Synthetic','model':'Report Sedan','status':'acquired','title_brand':'unknown','acquisition_cost':'5000.10','recon_cost':'100.20','revision':self.vehicle.revision}
        response=self.client.post(reverse('vehicle_edit',args=[self.vehicle.pk]),data)
        self.assertEqual(response.status_code,302)
        self.vehicle.refresh_from_db();self.assertEqual(self.vehicle.acquired_on,timezone.localdate()-timedelta(days=45))
        response=self.client.post(reverse('vehicle_edit',args=[self.vehicle.pk]),data|{'revision':self.vehicle.revision,'acquired_on':str(timezone.localdate()+timedelta(days=1))})
        self.assertContains(response,'Enter today or an earlier acquisition date.')

    def test_csv_export_filters_reversals_isolation_formula_safety_and_roles(self):
        import csv
        import io
        from datetime import timedelta
        viewer = get_user_model().objects.create_user('report-viewer')
        Membership.objects.create(user=viewer, dealership=self.dealer, role='viewer')

        today = timezone.localdate()
        # Add itemized cost and another cost that gets reversed
        entry1 = add_cost(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, data={'amount': Decimal('250.35'), 'category': 'repair', 'description': 'Retained repair', 'effective_on': today, 'request_key': uuid4()})
        entry2 = add_cost(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, data={'amount': Decimal('99.00'), 'category': 'parts', 'description': 'Reversed part', 'effective_on': today, 'request_key': uuid4()})
        reverse_cost(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, entry_id=entry2.pk, reason='Practice reversal', request_key=uuid4())

        # Vehicle with dangerous formula-like strings, unpriced asking_price=None, and future acquisition date
        formula_veh = Vehicle.objects.create(
            dealership=self.dealer, stock_number='=CMD()', year=2021, make='+SUM(1,2)',
            model='-IMPORT()', vin='@HYPERLINK()', status='recon',
            acquired_on=today + timedelta(days=2), acquisition_cost=Decimal('1000.00'),
            recon_cost=Decimal('50.00'), asking_price=None,
        )
        # Vehicle priced below recorded cost
        below_cost_veh = Vehicle.objects.create(
            dealership=self.dealer, stock_number='BELOW-1', year=2019, make='Synthetic',
            model='Compact', status='available', acquired_on=today - timedelta(days=10),
            acquisition_cost=Decimal('4000.00'), recon_cost=Decimal('0.00'), asking_price=Decimal('3500.00'),
        )

        export_url = reverse('inventory_investment_report_export')
        # Viewer is allowed to export read-only report; anonymous is redirected; disabled gate returns 404
        self.client.force_login(viewer)
        res = self.client.get(export_url, {'sort': 'cost_high'})
        self.assertEqual(res.status_code, 200)
        self.assertIn('no-store', res['Cache-Control'])
        self.assertEqual(res['Content-Security-Policy'], 'sandbox')
        self.assertIn('DEMO-inventory-investment-active.csv', res['Content-Disposition'])
        self.assertEqual(self.client.head(export_url).status_code, 200)
        self.assertEqual(self.client.post(export_url).status_code, 405)

        text = res.content.decode('utf-8-sig')
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual([r['stock_number'] for r in rows], ['RPT-1', 'BELOW-1', "'=CMD()"])
        self.assertNotIn('PRIVATE-REPORT', text)

        # Verify exact recorded cost after reversal on RPT-1: 5000.10 + 100.20 + 250.35 = 5350.65; asking 6000 - 5350.65 = 649.35
        rpt = rows[0]
        self.assertEqual(rpt['acquisition_cost_usd'], '5000.10')
        self.assertEqual(rpt['unitemized_recon_cost_usd'], '100.20')
        self.assertEqual(rpt['net_itemized_cost_usd'], '250.35')
        self.assertEqual(rpt['recorded_investment_usd'], '5350.65')
        self.assertEqual(rpt['asking_price_usd'], '6000.00')
        self.assertEqual(rpt['asking_less_recorded_cost_usd'], '649.35')
        self.assertEqual(rpt['acquisition_date_status'], 'not_entered')
        self.assertEqual(rpt['days_since_acquisition'], '')

        # Verify below-cost negative difference is escaped for CSV spreadsheet safety
        below = rows[1]
        self.assertEqual(below['days_since_acquisition'], '10')
        self.assertEqual(below['acquisition_date_status'], 'recorded')
        self.assertEqual(below['asking_less_recorded_cost_usd'], "'-500.00")

        # Verify formula-injection cells are prefixed with apostrophe and unknown asking_price stays blank
        danger = rows[2]
        self.assertEqual(danger['stock_number'], "'=CMD()")
        self.assertEqual(danger['make'], "'+SUM(1,2)")
        self.assertEqual(danger['model'], "'-IMPORT()")
        self.assertEqual(danger['vin'], "'@HYPERLINK()")
        self.assertEqual(danger['asking_price_usd'], '')
        self.assertEqual(danger['asking_less_recorded_cost_usd'], '')
        self.assertEqual(danger['acquisition_date_status'], 'future_date_review')
        self.assertEqual(danger['days_since_acquisition'], '')

        # Filtered export respects status, age, and q filters
        filtered_res = self.client.get(export_url, {'status': 'available', 'age': '0_30', 'q': 'BELOW'})
        filtered_rows = list(csv.DictReader(io.StringIO(filtered_res.content.decode('utf-8-sig'))))
        self.assertEqual([r['stock_number'] for r in filtered_rows], ['BELOW-1'])

        with override_settings(RECON_DEMO_ENABLED=False):
            self.assertEqual(self.client.get(export_url).status_code, 404)

    def test_sold_on_chronology_permissions_audit_and_time_to_sale_report(self):
        from datetime import timedelta
        from core.models import AuditEvent
        today = timezone.localdate()
        edit_url = reverse('vehicle_edit', args=[self.vehicle.pk])
        base_data = {
            'stock_number': self.vehicle.stock_number, 'year': 2020, 'make': 'Synthetic',
            'model': 'Report Sedan', 'status': 'available', 'title_brand': 'unknown',
            'acquisition_cost': '5000.10', 'recon_cost': '100.20',
        }

        # Reject sold_on when status is not sold
        res = self.client.post(edit_url, base_data | {'revision': self.vehicle.revision, 'sold_on': str(today)})
        self.assertContains(res, 'Record a sale date only when the vehicle status is Sold.')

        # Reject future sold_on
        res = self.client.post(edit_url, base_data | {'revision': self.vehicle.revision, 'status': 'sold', 'sold_on': str(today + timedelta(days=1))})
        self.assertContains(res, 'Enter today or an earlier sale date.')

        # Reject sold_on earlier than acquired_on
        acq_date = today - timedelta(days=20)
        res = self.client.post(edit_url, base_data | {
            'revision': self.vehicle.revision, 'status': 'sold',
            'acquired_on': str(acq_date), 'sold_on': str(acq_date - timedelta(days=1)),
        })
        self.assertContains(res, 'Sale date must be on or after the acquisition date.')

        # Valid chronological sold_on saves, increments revision, records audit event, and preserves on legacy POST
        sale_date = today - timedelta(days=5)
        res = self.client.post(edit_url, base_data | {
            'revision': self.vehicle.revision, 'status': 'sold',
            'acquired_on': str(acq_date), 'sold_on': str(sale_date),
        })
        self.assertEqual(res.status_code, 302)
        self.vehicle.refresh_from_db()
        self.assertEqual((self.vehicle.acquired_on, self.vehicle.sold_on, self.vehicle.revision), (acq_date, sale_date, 2))
        event = AuditEvent.objects.filter(vehicle=self.vehicle).first()
        self.assertEqual(event.changes['sold_on']['after'], str(sale_date))

        # Omitted sold_on in legacy submission preserves existing sold_on
        res = self.client.post(edit_url, base_data | {'revision': self.vehicle.revision, 'status': 'sold'})
        self.assertEqual(res.status_code, 302)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.sold_on, sale_date)

        # Create additional sold vehicles to test time-to-sale buckets and unknown/non-chronological edge cases
        sold_45 = Vehicle.objects.create(
            dealership=self.dealer, stock_number='SOLD-45', year=2020, make='Synthetic', model='Mid',
            status='sold', acquired_on=today - timedelta(days=50), sold_on=today - timedelta(days=5),
        )
        sold_no_acq = Vehicle.objects.create(
            dealership=self.dealer, stock_number='SOLD-NO-ACQ', year=2020, make='Synthetic', model='NoAcq',
            status='sold', acquired_on=None, sold_on=today - timedelta(days=2),
        )
        sold_bad_order = Vehicle.objects.create(
            dealership=self.dealer, stock_number='SOLD-BAD-CHRON', year=2020, make='Synthetic', model='BadChron',
            status='sold', acquired_on=today - timedelta(days=5), sold_on=today - timedelta(days=15),
        )
        Vehicle.objects.create(
            dealership=self.other, stock_number='FOREIGN-SOLD', year=2020, make='Foreign', model='Sold',
            status='sold', acquired_on=today - timedelta(days=20), sold_on=today - timedelta(days=5),
        )

        report_url = reverse('inventory_investment_report')
        sold_res = self.client.get(report_url, {'status': 'sold'})
        self.assertContains(sold_res, 'Time to sale: 15 days')
        self.assertContains(sold_res, 'Time to sale: 45 days')
        self.assertContains(sold_res, 'Acquisition date needed for time to sale')
        self.assertContains(sold_res, 'Sale date · review chronology')
        self.assertNotContains(sold_res, 'FOREIGN-SOLD')

        # Filter by time-to-sale buckets
        tts_0_30 = self.client.get(report_url, {'status': 'sold', 'tts': '0_30'})
        self.assertEqual([v.pk for v in tts_0_30.context['vehicles']], [self.vehicle.pk])
        tts_31_60 = self.client.get(report_url, {'status': 'sold', 'tts': '31_60'})
        self.assertEqual([v.pk for v in tts_31_60.context['vehicles']], [sold_45.pk])
        tts_unknown = self.client.get(report_url, {'status': 'sold', 'tts': 'unknown'})
        self.assertCountEqual([v.pk for v in tts_unknown.context['vehicles']], [sold_no_acq.pk, sold_bad_order.pk])

        # Exact bucket boundary and database-side filtering check (no pk__in query)
        sold_0 = Vehicle.objects.create(dealership=self.dealer, stock_number='SOLD-0', year=2020, make='Synthetic', model='B', status='sold', acquired_on=today - timedelta(days=10), sold_on=today - timedelta(days=10))
        sold_30 = Vehicle.objects.create(dealership=self.dealer, stock_number='SOLD-30', year=2020, make='Synthetic', model='B', status='sold', acquired_on=today - timedelta(days=40), sold_on=today - timedelta(days=10))
        sold_31 = Vehicle.objects.create(dealership=self.dealer, stock_number='SOLD-31', year=2020, make='Synthetic', model='B', status='sold', acquired_on=today - timedelta(days=41), sold_on=today - timedelta(days=10))
        sold_60 = Vehicle.objects.create(dealership=self.dealer, stock_number='SOLD-60', year=2020, make='Synthetic', model='B', status='sold', acquired_on=today - timedelta(days=70), sold_on=today - timedelta(days=10))
        sold_61 = Vehicle.objects.create(dealership=self.dealer, stock_number='SOLD-61', year=2020, make='Synthetic', model='B', status='sold', acquired_on=today - timedelta(days=71), sold_on=today - timedelta(days=10))
        sold_90 = Vehicle.objects.create(dealership=self.dealer, stock_number='SOLD-90', year=2020, make='Synthetic', model='B', status='sold', acquired_on=today - timedelta(days=100), sold_on=today - timedelta(days=10))
        sold_91 = Vehicle.objects.create(dealership=self.dealer, stock_number='SOLD-91', year=2020, make='Synthetic', model='B', status='sold', acquired_on=today - timedelta(days=101), sold_on=today - timedelta(days=10))
        sold_future = Vehicle.objects.create(dealership=self.dealer, stock_number='SOLD-FUT', year=2020, make='Synthetic', model='B', status='sold', acquired_on=today - timedelta(days=10), sold_on=today + timedelta(days=1))

        self.assertCountEqual([v.pk for v in self.client.get(report_url, {'status': 'sold', 'tts': '0_30'}).context['vehicles']], [self.vehicle.pk, sold_0.pk, sold_30.pk])
        self.assertCountEqual([v.pk for v in self.client.get(report_url, {'status': 'sold', 'tts': '31_60'}).context['vehicles']], [sold_45.pk, sold_31.pk, sold_60.pk])
        self.assertCountEqual([v.pk for v in self.client.get(report_url, {'status': 'sold', 'tts': '61_90'}).context['vehicles']], [sold_61.pk, sold_90.pk])
        self.assertCountEqual([v.pk for v in self.client.get(report_url, {'status': 'sold', 'tts': 'over_90'}).context['vehicles']], [sold_91.pk])
        self.assertCountEqual([v.pk for v in self.client.get(report_url, {'status': 'sold', 'tts': 'unknown'}).context['vehicles']], [sold_no_acq.pk, sold_bad_order.pk, sold_future.pk])
        self.assertNotIn(' IN (', str(self.client.get(report_url, {'status': 'sold', 'tts': '0_30'}).context['page_obj'].paginator.object_list.query))

    def test_report_accessibility_semantics_labels_and_empty_filter_reset(self):
        url = reverse('inventory_investment_report')
        res = self.client.get(url)
        self.assertContains(res, 'role="table"')
        self.assertContains(res, 'scope="row" role="rowheader"')
        self.assertContains(res, 'class="investment-cell-label" aria-hidden="true"')
        self.assertContains(res, 'role="status" aria-live="polite"')
        self.assertContains(res, 'aria-label="Filter inventory investment report"')
        self.assertContains(res, 'aria-label="Work and costs for stock RPT-1: $5,100.30"')

        empty_filtered = self.client.get(url, {'q': 'NONEXISTENT-STOCK-999'})
        self.assertContains(empty_filtered, 'No vehicles match these filters.')
        self.assertContains(empty_filtered, f'<a href="{url}">Reset filters</a>')

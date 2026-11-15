# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from datetime import timedelta
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import AuditEvent, Dealership, Membership, SavedView
from .forms import VehicleForm
from .models import Vehicle, ReconTask, VehicleVendor
from .reconditioning import add_cost, reverse_cost


@override_settings(RECON_DEMO_ENABLED=True)
class PricingAndQueueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealership.objects.create(name='Synthetic pricing dealer')
        cls.other = Dealership.objects.create(name='Other synthetic pricing dealer')
        cls.user = get_user_model().objects.create_user(username='pricing-staff')
        cls.viewer = get_user_model().objects.create_user(username='pricing-viewer')
        Membership.objects.create(user=cls.user, dealership=cls.dealer, role='staff')
        Membership.objects.create(user=cls.viewer, dealership=cls.dealer, role='viewer')
        cls.vehicle = Vehicle.objects.create(dealership=cls.dealer, stock_number='PRICE-1', year=2021, make='Synthetic', model='Price Sedan', acquisition_cost=Decimal('5000.10'), recon_cost=Decimal('100.20'), asking_price=Decimal('6995.00'))
        cls.foreign = Vehicle.objects.create(dealership=cls.other, stock_number='PRIVATE-OTHER', year=2022, make='Other', model='Private', asking_price=Decimal('9900.25'))
        cls.vendor = VehicleVendor.objects.create(dealership=cls.dealer, name='Practice Tire Shop', normalized_name='practice tire shop', created_by=cls.user)
        cls.todo = ReconTask.objects.create(vehicle=cls.vehicle, title='Replace tires', vendor=cls.vendor, created_by=cls.user)
        cls.started = ReconTask.objects.create(vehicle=cls.vehicle, title='Detail cabin', status='in_progress', created_by=cls.user)
        cls.done = ReconTask.objects.create(vehicle=cls.vehicle, title='Inspect lights', status='done', created_by=cls.user)
        ReconTask.objects.create(vehicle=cls.foreign, title='Private foreign work', created_by=cls.user)

    def setUp(self):
        self.client.force_login(self.user)

    def vehicle_data(self, **changes):
        return {'stock_number':self.vehicle.stock_number, 'year':2021, 'make':'Synthetic', 'model':'Price Sedan', 'status':'recon', 'title_brand':'unknown', 'acquisition_cost':'5000.10', 'recon_cost':'100.20', 'revision':self.vehicle.revision, **changes}

    def test_reference_asking_difference_after_cost_and_correction(self):
        data={'amount':Decimal('250.35'), 'category':'repair', 'description':'Synthetic repair', 'effective_on':timezone.localdate(), 'request_key':uuid4()}
        entry=add_cost(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, data=data)
        self.assertEqual(self.vehicle.asking_less_cost, Decimal('1644.35'))
        reverse_cost(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, entry_id=entry.pk, reason='Practice correction', request_key=uuid4())
        self.assertEqual(self.vehicle.asking_less_cost, Decimal('1894.70'))
        response=self.client.get(reverse('vehicle_recon',args=[self.vehicle.pk]))
        self.assertContains(response,'Asking price less recorded costs')
        self.assertContains(response,'1,894.70')
        self.assertNotContains(response,'Net profit')

    def test_unknown_and_zero_prices_are_distinct(self):
        self.vehicle.asking_price=None
        self.assertIsNone(self.vehicle.asking_less_cost)
        self.vehicle.asking_price=Decimal('0')
        self.assertEqual(self.vehicle.asking_less_cost,Decimal('-5100.30'))
        self.vehicle.save()
        response=self.client.get(reverse('vehicle_recon',args=[self.vehicle.pk]))
        self.assertContains(response,'Below recorded costs')
        self.assertContains(response,'price-below-cost')

    def test_old_post_preserves_price_and_explicit_blank_clears_it(self):
        response=self.client.post(reverse('vehicle_edit',args=[self.vehicle.pk]),self.vehicle_data())
        self.assertEqual(response.status_code,302)
        self.vehicle.refresh_from_db(); self.assertEqual(self.vehicle.asking_price,Decimal('6995.00'))
        response=self.client.post(reverse('vehicle_edit',args=[self.vehicle.pk]),self.vehicle_data(asking_price=''))
        self.assertEqual(response.status_code,302)
        self.vehicle.refresh_from_db(); self.assertIsNone(self.vehicle.asking_price)
        event=AuditEvent.objects.filter(vehicle=self.vehicle).first()
        self.assertEqual(event.changes['asking_price'],{'before':'6995.00','after':'None'})

    def test_price_validation_audit_and_stale_revision(self):
        for invalid in ['-1','1.001','NaN','10000000000']:
            response=self.client.post(reverse('vehicle_edit',args=[self.vehicle.pk]),self.vehicle_data(asking_price=invalid))
            self.assertTrue(response.context['form']['asking_price'].errors)
        response=self.client.post(reverse('vehicle_edit',args=[self.vehicle.pk]),self.vehicle_data(asking_price='7250.25'))
        self.assertEqual(response.status_code,302)
        self.assertEqual(AuditEvent.objects.get(vehicle=self.vehicle).changes['asking_price']['after'],'7250.25')
        response=self.client.post(reverse('vehicle_edit',args=[self.vehicle.pk]),self.vehicle_data(asking_price='7000.00'))
        self.assertEqual(response.status_code,409)
        self.vehicle.refresh_from_db(); self.assertEqual(self.vehicle.asking_price,Decimal('7250.25'))
        with self.assertRaises(DatabaseError), transaction.atomic():
            Vehicle.objects.filter(pk=self.vehicle.pk).update(asking_price=-1)

    def test_new_vehicle_defaults_unpriced(self):
        form=VehicleForm(self.vehicle_data(stock_number='NEW-UNPRICED'),dealership=self.dealer)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertIsNone(form.cleaned_data['asking_price'])

    def test_inventory_asking_filter_and_new_deal_suggestion(self):
        response=self.client.get(reverse('inventory'),{'filter_field':'asking','filter_op':'between','filter_value':'6995.00','filter_to':'6995.00'})
        self.assertEqual([v.pk for v in response.context['vehicles']],[self.vehicle.pk])
        self.assertContains(response,'6,995.00')
        self.assertContains(response,reverse('recon_queue'))
        response=self.client.get(reverse('deal_create'),{'vehicle':self.vehicle.pk})
        self.assertEqual(response.context['form']['sale_price'].value(),Decimal('6995.00'))
        response=self.client.get(reverse('deal_create'),{'vehicle':self.foreign.pk})
        self.assertIsNone(response.context['form']['vehicle'].value())
        self.assertNotEqual(response.context['form']['sale_price'].value(),Decimal('9900.25'))

    def test_open_done_and_all_queue_scopes(self):
        route=reverse('recon_queue')
        response=self.client.get(route)
        self.assertEqual([t.pk for t in response.context['work']],[self.todo.pk,self.started.pk])
        self.assertNotContains(response,'Private foreign work')
        self.assertEqual(response['Cache-Control'],'private, no-store')
        response=self.client.get(route,{'scope':'done'})
        self.assertEqual([t.pk for t in response.context['work']],[self.done.pk])
        response=self.client.get(route,{'scope':'all'})
        self.assertEqual(response.context['page_obj'].paginator.count,3)

    def test_vendor_search_rules_invalid_filters_and_preserved_tabs(self):
        route=reverse('recon_queue')
        params={'q':'Synthetic tires','filter_field':'vendor','filter_op':'contains','filter_value':'Tire','sort':'vehicle'}
        response=self.client.get(route,params)
        self.assertEqual([t.pk for t in response.context['work']],[self.todo.pk])
        for tab in response.context['tabs']:
            self.assertIn('filter_value=Tire',tab['query']); self.assertIn('sort=vehicle',tab['query'])
        response=self.client.get(route,{'scope':'invented'})
        self.assertTrue(response.context['filter_state'].errors)
        self.assertEqual(response.context['page_obj'].paginator.count,0)

    def test_saved_queue_view_is_personal_scoped_and_gated(self):
        view=SavedView.objects.create(dealership=self.dealer,owner=self.user,resource='reconditioning',name='Practice open tires',parameters={'q':['tires'],'scope':['open']})
        response=self.client.get(reverse('recon_queue'),{'view':view.pk})
        self.assertEqual([t.pk for t in response.context['work']],[self.todo.pk])
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('recon_queue'),{'view':view.pk}).status_code,404)
        response=self.client.get(reverse('recon_queue'))
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,reverse('vehicle_create'))
        with override_settings(RECON_DEMO_ENABLED=False):
            self.assertEqual(self.client.get(reverse('recon_queue')).status_code,404)
            self.assertEqual(self.client.get(reverse('saved_view_create',args=['reconditioning'])).status_code,404)

    def test_sold_vehicle_open_work_remains_visible(self):
        self.vehicle.status='sold'; self.vehicle.save()
        response=self.client.get(reverse('recon_queue'))
        self.assertContains(response,'Replace tires')
        self.assertContains(response,'Sold vehicle')

    def test_queue_paginates_stably(self):
        ReconTask.objects.bulk_create([ReconTask(vehicle=self.vehicle,title=f'Practice task {n}',created_by=self.user) for n in range(30)])
        first=self.client.get(reverse('recon_queue'))
        second=self.client.get(reverse('recon_queue'),{'page':2})
        first_ids={t.pk for t in first.context['work']}
        second_ids={t.pk for t in second.context['work']}
        self.assertEqual(len(first_ids),25);self.assertEqual(len(second_ids),7)
        self.assertFalse(first_ids & second_ids)

    def test_workload_summary_counts_filtered_status_and_local_due_dates(self):
        today = timezone.localdate()
        ReconTask.objects.filter(pk=self.todo.pk).update(due_on=today - timedelta(days=1))
        ReconTask.objects.filter(pk=self.started.pk).update(due_on=today)
        ReconTask.objects.filter(pk=self.done.pk).update(due_on=today - timedelta(days=2))
        ReconTask.objects.create(vehicle=self.vehicle, title='Unscheduled practice', created_by=self.user)
        ReconTask.objects.create(vehicle=self.vehicle, title='Finished unscheduled', status='done', created_by=self.user)
        ReconTask.objects.create(vehicle=self.foreign, title='Foreign overdue', due_on=today - timedelta(days=1), created_by=self.user)
        response = self.client.get(reverse('recon_queue'), {'scope': 'all'})
        self.assertEqual(response.context['summary'], {'open': 3, 'in_progress': 1, 'done': 2, 'overdue': 1, 'unscheduled': 1})
        self.assertContains(response, 'Work matching this view')
        self.assertContains(response, 'Overdue means an open task with a target date before today.')
        self.assertContains(response, 'These counts are not safety approval or accounting.')
        self.assertNotContains(response, 'Foreign overdue')
        response = self.client.get(reverse('recon_queue'), {'scope': 'done'})
        self.assertEqual(response.context['summary'], {'open': 0, 'in_progress': 0, 'done': 2, 'overdue': 0, 'unscheduled': 0})
        response = self.client.get(reverse('recon_queue'), {'scope': 'all', 'q': 'no matching work'})
        self.assertEqual(response.context['summary'], {'open': 0, 'in_progress': 0, 'done': 0, 'overdue': 0, 'unscheduled': 0})
        response = self.client.get(reverse('recon_queue'), {'scope': 'invented'})
        self.assertContains(response, 'Correct the filters to see the workload summary.')
        self.assertNotContains(response, 'Work matching this view')

    def test_workload_summary_covers_all_filtered_pages_and_saved_views(self):
        today = timezone.localdate()
        ReconTask.objects.bulk_create([
            ReconTask(vehicle=self.vehicle, title=f'Batch work {n}', created_by=self.user,
                      status='in_progress' if n < 10 else 'todo',
                      due_on=today - timedelta(days=1) if n < 12 else None)
            for n in range(30)
        ])
        ReconTask.objects.create(vehicle=self.foreign, title='Batch work foreign', created_by=self.user)
        view = SavedView.objects.create(dealership=self.dealer, owner=self.user, resource='reconditioning',
                                        name='Practice batch', parameters={'q': ['Batch work'], 'scope': ['all']})
        expected = {'open': 30, 'in_progress': 10, 'done': 0, 'overdue': 12, 'unscheduled': 18}
        first = self.client.get(reverse('recon_queue'), {'view': view.pk})
        second = self.client.get(reverse('recon_queue'), {'view': view.pk, 'page': 2})
        self.assertEqual(first.context['summary'], expected)
        self.assertEqual(second.context['summary'], expected)
        self.assertEqual(first.context['page_obj'].paginator.count, 30)
        self.assertEqual(len(first.context['work']), 25)
        self.assertEqual(len(second.context['work']), 5)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('recon_queue'), {'view': view.pk}).status_code, 404)
        self.assertEqual(self.client.get(reverse('recon_queue'), {'scope': 'all', 'q': 'Batch work'}).context['summary'], expected)
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse('recon_queue')).status_code, 200)

    def test_inventory_price_changes_never_rewrite_existing_deal(self):
        from customers.models import Customer
        from deals.models import DraftDeal
        buyer=Customer.objects.create(dealership=self.dealer,first_name='Practice',last_name='Buyer')
        deal=DraftDeal.objects.create(dealership=self.dealer,vehicle=self.vehicle,buyer=buyer,sale_price=Decimal('6750.00'))
        response=self.client.post(reverse('vehicle_edit',args=[self.vehicle.pk]),self.vehicle_data(asking_price='7250.25'))
        self.assertEqual(response.status_code,302)
        deal.refresh_from_db();self.assertEqual(deal.sale_price,Decimal('6750.00'))

    def test_keyword_form_data_preserves_omitted_price(self):
        form=VehicleForm(data=self.vehicle_data(),instance=self.vehicle,dealership=self.dealer)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['asking_price'],Decimal('6995.00'))

    def test_queue_accessibility_semantics_labels_and_empty_filter_reset(self):
        route = reverse('recon_queue')
        res = self.client.get(route)
        self.assertContains(res, 'role="table"')
        self.assertContains(res, 'scope="row" role="rowheader"')
        self.assertContains(res, 'class="recon-cell-label" aria-hidden="true"')
        self.assertNotContains(res, 'recon-mobile-status')
        self.assertContains(res, 'class="recon-status status-todo"')
        self.assertContains(res, 'aria-label="Edit work: Replace tires (Stock PRICE-1)"')
        self.assertContains(res, 'aria-label="Work views"')
        self.assertContains(res, 'aria-label="Target date filters"')
        self.assertContains(res, 'aria-label="Task age filters"')

        empty_filtered = self.client.get(route, {'q': 'NONEXISTENT-WORK-999'})
        self.assertContains(empty_filtered, 'No work matches these filters.')
        self.assertContains(empty_filtered, f'<a href="{route}">Reset filters</a>')

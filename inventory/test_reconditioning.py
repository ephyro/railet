# SPDX-License-Identifier: MPL-2.0
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import AuditEvent, Dealership, Membership
from .models import Vehicle, VehicleVendor, VehicleVendorEvent, VehicleCostEntry, ReconTask
from .reconditioning import add_cost, add_task, edit_task, change_task, reverse_cost, save_vendor, with_cost_totals


@override_settings(RECON_DEMO_ENABLED=True)
class ReconTests(TestCase):
    def setUp(self):
        self.dealer = Dealership.objects.create(name='Synthetic recon shop')
        self.other = Dealership.objects.create(name='Other synthetic shop')
        self.user = get_user_model().objects.create_user(username='recon-staff')
        self.member = Membership.objects.create(user=self.user, dealership=self.dealer, role='staff')
        self.vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='RECON-1', year=2020, make='Synthetic', model='Workshop', acquisition_cost=Decimal('5000.10'), recon_cost=Decimal('100.20'))
        self.foreign = Vehicle.objects.create(dealership=self.other, stock_number='OTHER', year=2020, make='Synthetic', model='Other')
        self.client.force_login(self.user)

    def data(self, **changes):
        return dict(amount=Decimal('250.35'), category='repair', description='Synthetic brake repair', effective_on=timezone.localdate(), request_key=uuid4(), vendor='', new_vendor='', task='', **changes)

    def cost(self, data=None):
        return add_cost(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, data=data or self.data())

    def task(self, **changes):
        data={'title': 'Replace tires', 'request_key': uuid4(), 'new_vendor': 'Practice Garage', **changes}
        return add_task(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, data=data)

    def test_existing_costs_unchanged_and_independent_reference_total(self):
        self.assertEqual(self.vehicle.total_cost, Decimal('5100.30'))
        self.cost()
        self.assertEqual(self.vehicle.total_cost, Decimal('5350.65'))
        fresh = with_cost_totals(Vehicle.objects.all()).get(pk=self.vehicle.pk)
        self.assertEqual(fresh.total_cost, Decimal('5350.65'))
        self.assertEqual((fresh.acquisition_cost, fresh.recon_cost), (Decimal('5000.10'), Decimal('100.20')))
        response = self.client.get(reverse('inventory'), {'filter_field': 'cost', 'filter_op': 'eq', 'filter_value': '5350.65'})
        self.assertEqual([v.pk for v in response.context['vehicles']], [self.vehicle.pk])
        self.assertContains(response, '5,350.65')

    def test_vendor_reuse_task_status_and_audit(self):
        task = self.task()
        entry = self.cost(self.data() | {'new_vendor': '  practice   GARAGE ', 'task': task})
        self.assertEqual(entry.vendor_id, task.vendor_id)
        self.assertEqual(entry.vendor_name, 'Practice Garage')
        change_task(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, task_id=task.pk, revision=1, status='in_progress')
        task.refresh_from_db(); self.assertEqual((task.status, task.revision), ('in_progress', 2))
        with self.assertRaises(ValidationError):
            change_task(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, task_id=task.pk, revision=1, status='done')
        change_task(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, task_id=task.pk, revision=2, status='done')
        self.assertEqual(AuditEvent.objects.filter(vehicle=self.vehicle).count(), 4)

    def test_duplicate_cost_and_task_save_are_idempotent(self):
        data = self.data(); first = self.cost(data)
        self.assertEqual(first.pk, self.cost(data).pk)
        with self.assertRaises(ValidationError): self.cost(data | {'amount': Decimal('9')})
        task_data={'title': 'Detail', 'request_key': uuid4(), 'new_vendor': 'Practice Detail'}
        task = add_task(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, data=task_data)
        self.assertEqual(task.pk, add_task(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, data=task_data).pk)
        self.assertEqual(VehicleCostEntry.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.count(), 2)
        with self.assertRaises(ValidationError):
            add_task(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, data=task_data | {'title':'Different work'})
        with self.assertRaises(ValidationError): self.cost(data | {'new_vendor':'Different Garage'})

    def test_reversal_exact_retained_and_retry(self):
        entry = self.cost(); key = uuid4()
        kwargs=dict(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, entry_id=entry.pk, reason='Duplicate synthetic invoice', request_key=key)
        reversal = reverse_cost(**kwargs)
        self.assertEqual(reverse_cost(**kwargs).pk, reversal.pk)
        self.assertEqual((reversal.amount_cents, reversal.debit, reversal.credit, reversal.reverses_id), (25035, 'cost_offset', 'vehicle_cost', entry.pk))
        self.assertEqual(self.vehicle.total_cost, Decimal('5100.30'))
        self.assertEqual(VehicleCostEntry.objects.count(), 2)
        with self.assertRaises(ValidationError): reverse_cost(**(kwargs | {'request_key': uuid4()}))
        with self.assertRaises(ValidationError): reverse_cost(**(kwargs | {'reason':'Changed reason'}))
        response=self.client.get(reverse('vehicle_recon', args=[self.vehicle.pk]))
        self.assertContains(response, f'Reverses #{entry.pk}')
        self.assertContains(response, 'Duplicate synthetic invoice')

    def test_database_rejects_mutation_deletion_and_invalid_legs(self):
        entry = self.cost()
        for action in [lambda: VehicleCostEntry.objects.filter(pk=entry.pk).update(amount_cents=2), lambda: VehicleCostEntry.objects.filter(pk=entry.pk).delete()]:
            with self.assertRaises(DatabaseError), transaction.atomic(): action()
        with self.assertRaises(DatabaseError), transaction.atomic():
            VehicleCostEntry.objects.create(vehicle=self.vehicle, actor=self.user, kind='cost', category='repair', description='Unbalanced', amount_cents=20, credit='vehicle_cost', effective_on=timezone.localdate())

    def test_database_rejects_inexact_and_cross_vehicle_reversals(self):
        entry=self.cost()
        for changes in [{'amount_cents':1}, {'vehicle':self.foreign}, {'description':'Changed'}, {'reason':''}]:
            values=dict(vehicle=self.vehicle, actor=self.user, kind='reversal', category=entry.category, description=entry.description, amount_cents=entry.amount_cents, debit='cost_offset', credit='vehicle_cost', reverses=entry, effective_on=entry.effective_on, reason='Synthetic correction') | changes
            with self.assertRaises(DatabaseError), transaction.atomic(): VehicleCostEntry.objects.create(**values)

    def test_vendor_and_task_isolation_service_and_database(self):
        vendor=VehicleVendor.objects.create(dealership=self.other, name='Private vendor', normalized_name='private vendor', created_by=self.user)
        foreign_task=ReconTask.objects.create(vehicle=self.foreign, title='Other work', created_by=self.user)
        for changes in [{'vendor':vendor}, {'task':foreign_task}]:
            with self.assertRaises(ValidationError): self.cost(self.data() | changes)
            with self.assertRaises(DatabaseError), transaction.atomic():
                VehicleCostEntry.objects.create(vehicle=self.vehicle, actor=self.user, kind='cost', category='repair', description='Invalid scope', amount_cents=20, effective_on=timezone.localdate(), **changes)
        response=self.client.post(reverse('vehicle_cost_create',args=[self.vehicle.pk]), self.data() | {'vendor':vendor.pk})
        self.assertContains(response,'Select a valid choice')
        self.assertFalse(VehicleCostEntry.objects.exists())

    def test_invalid_money_and_date_fail_closed(self):
        for amount in [Decimal('0'), Decimal('-1'), Decimal('1.001'), Decimal('NaN'), 1.25, Decimal('10000000000')]:
            with self.assertRaises(ValidationError): self.cost(self.data() | {'amount':amount})
        with self.assertRaises(ValidationError): self.cost(self.data() | {'effective_on':timezone.localdate()+timedelta(days=1)})
        self.assertFalse(VehicleCostEntry.objects.exists())

    def test_permissions_gates_and_csrf(self):
        self.assertEqual(self.client.get(reverse('vehicle_recon',args=[self.foreign.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse('vehicle_cost_create',args=[self.foreign.pk]), self.data()).status_code,404)
        self.member.role='viewer'; self.member.save()
        self.assertEqual(self.client.get(reverse('vehicle_recon',args=[self.vehicle.pk])).status_code,200)
        self.assertEqual(self.client.post(reverse('vehicle_cost_create',args=[self.vehicle.pk]),self.data()).status_code,403)
        with self.assertRaises(PermissionDenied): self.cost()
        with override_settings(RECON_DEMO_ENABLED=False):
            self.assertEqual(self.client.get(reverse('vehicle_recon',args=[self.vehicle.pk])).status_code,404)
            with self.assertRaises(PermissionDenied): self.cost()
        client=Client(enforce_csrf_checks=True); client.force_login(self.user)
        self.assertEqual(client.post(reverse('vehicle_cost_create',args=[self.vehicle.pk]),self.data()).status_code,403)

    def test_audit_failure_rolls_back_cost_and_new_vendor(self):
        with patch('inventory.reconditioning.AuditEvent.objects.create',side_effect=RuntimeError('Audit unavailable')):
            with self.assertRaises(RuntimeError): self.cost(self.data() | {'new_vendor':'Rollback Garage'})
        self.assertFalse(VehicleCostEntry.objects.exists())
        self.assertFalse(VehicleVendor.objects.exists())

    def test_browser_routes_errors_and_status_conflict(self):
        task=self.task()
        for route in ['vehicle_recon','recon_task_create','vehicle_cost_create']:
            self.assertEqual(self.client.get(reverse(route,args=[self.vehicle.pk])).status_code,200)
        response=self.client.post(reverse('vehicle_cost_create',args=[self.vehicle.pk]), self.data() | {'amount':'-1','description':'Keep my description'})
        self.assertContains(response,'Keep my description'); self.assertContains(response,'data-error-summary')
        response=self.client.post(reverse('recon_task_status',args=[self.vehicle.pk,task.pk]),{'revision':1,'status':'in_progress'})
        self.assertEqual(response.status_code,302)
        response=self.client.post(reverse('recon_task_status',args=[self.vehicle.pk,task.pk]),{'revision':1,'status':'done'})
        self.assertContains(response,'This task changed',status_code=409)
        entry=self.cost()
        response=self.client.get(reverse('vehicle_cost_reverse',args=[self.vehicle.pk,entry.pk]))
        self.assertContains(response,'Reverse $250.35')
        self.assertEqual(response['Cache-Control'],'private, no-store')

    def test_task_edit_assignment_schedule_history_and_stale_guard(self):
        coworker = get_user_model().objects.create_user(username='recon-owner')
        Membership.objects.create(user=coworker, dealership=self.dealer, role='owner')
        viewer = get_user_model().objects.create_user(username='recon-viewer')
        Membership.objects.create(user=viewer, dealership=self.dealer, role='viewer')
        foreign_staff = get_user_model().objects.create_user(username='foreign-recon-staff')
        Membership.objects.create(user=foreign_staff, dealership=self.other, role='staff')

        due = timezone.localdate() - timedelta(days=2)
        task = self.task(detail='Check front pads', assigned_to=self.user, due_on=due)
        self.assertEqual((task.detail, task.assigned_to, task.due_on), ('Check front pads', self.user, due))

        edit_url = reverse('recon_task_edit', args=[self.vehicle.pk, task.pk])
        self.assertEqual(self.client.get(edit_url).status_code, 200)
        self.assertEqual(self.client.get(reverse('recon_task_edit', args=[self.foreign.pk, task.pk])).status_code, 404)

        # Foreign or viewer assignee is rejected; form preserves entered text
        for invalid_user in (foreign_staff, viewer):
            bad = self.client.post(edit_url, {
                'revision': task.revision, 'title': 'Keep edited title', 'detail': 'Keep edited detail',
                'status': 'in_progress', 'vendor': task.vendor_id, 'new_vendor': '',
                'assigned_to': invalid_user.pk, 'due_on': due.isoformat(),
            })
            self.assertEqual(bad.status_code, 200)
            self.assertContains(bad, 'Keep edited title')
            self.assertContains(bad, 'data-error-summary')
            with self.assertRaises(ValidationError):
                edit_task(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, task_id=task.pk, data={
                    'revision': task.revision, 'title': 'Updated', 'detail': '', 'status': 'todo',
                    'vendor': None, 'new_vendor': '', 'assigned_to': invalid_user, 'due_on': None,
                })

        # Valid edit updates task, increments revision, records audit event, and does not change vehicle status
        next_due = timezone.localdate() + timedelta(days=5)
        res = self.client.post(edit_url, {
            'revision': 1, 'title': 'Replace front and rear tires', 'detail': 'Balanced and aligned',
            'status': 'in_progress', 'vendor': '', 'new_vendor': 'Alignment Shop',
            'assigned_to': coworker.pk, 'due_on': next_due.isoformat(),
        })
        self.assertEqual(res.status_code, 302)
        task.refresh_from_db()
        self.vehicle.refresh_from_db()
        self.assertEqual(task.title, 'Replace front and rear tires')
        self.assertEqual(task.detail, 'Balanced and aligned')
        self.assertEqual(task.status, 'in_progress')
        self.assertEqual(task.assigned_to, coworker)
        self.assertEqual(task.due_on, next_due)
        self.assertEqual(task.revision, 2)
        self.assertEqual(self.vehicle.status, 'acquired')

        event = AuditEvent.objects.filter(vehicle=self.vehicle, action='recon_task_updated').get()
        self.assertEqual(event.changes['title'], {'before': 'Replace tires', 'after': 'Replace front and rear tires'})
        self.assertEqual(event.changes['assigned_to_id'], {'before': self.user.pk, 'after': coworker.pk})

        # No-op edit does not increment revision or create duplicate audit event
        noop = self.client.post(edit_url, {
            'revision': 2, 'title': task.title, 'detail': task.detail,
            'status': task.status, 'vendor': task.vendor_id, 'new_vendor': '',
            'assigned_to': coworker.pk, 'due_on': next_due.isoformat(),
        })
        self.assertEqual(noop.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.revision, 2)
        self.assertEqual(AuditEvent.objects.filter(vehicle=self.vehicle, action='recon_task_updated').count(), 1)

        # Stale edit returns 409 and preserves user entries without overwriting
        stale = self.client.post(edit_url, {
            'revision': 1, 'title': 'Stale overwrite attempt', 'detail': 'Unsaved note',
            'status': 'done', 'vendor': task.vendor_id, 'new_vendor': '',
            'assigned_to': '', 'due_on': '',
        })
        self.assertContains(stale, 'Stale overwrite attempt', status_code=409)
        self.assertContains(stale, 'data-error-summary', status_code=409)
        task.refresh_from_db()
        self.assertEqual(task.title, 'Replace front and rear tires')

        # Audit failure rolls back task update and new vendor
        with patch('inventory.reconditioning.AuditEvent.objects.create', side_effect=RuntimeError('audit down')):
            with self.assertRaises(RuntimeError):
                self.client.post(edit_url, {
                    'revision': 2, 'title': 'Rolled back title', 'detail': '',
                    'status': 'done', 'vendor': '', 'new_vendor': 'Rollback Vendor',
                    'assigned_to': '', 'due_on': '',
                })
        task.refresh_from_db()
        self.assertEqual((task.title, task.revision), ('Replace front and rear tires', 2))
        self.assertFalse(VehicleVendor.objects.filter(normalized_name='rollback vendor').exists())

        # Queue search/filter by assignee, detail, and target date
        queue_res = self.client.get(reverse('recon_queue'), {
            'q': 'Balanced recon-owner', 'filter_field': 'assignee', 'filter_op': 'eq',
            'filter_value': 'recon-owner', 'sort': 'due',
        })
        self.assertEqual([t.pk for t in queue_res.context['work']], [task.pk])
        self.assertContains(queue_res, 'Assigned to recon-owner')

        # Viewer cannot access edit view
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(edit_url).status_code, 403)
        self.assertEqual(self.client.post(edit_url, {'revision': 2, 'title': 'No'}).status_code, 403)

    def test_queue_schedule_aging_and_vehicle_acquisition_filters(self):
        today = timezone.localdate()
        now = timezone.now()
        old_vehicle = Vehicle.objects.create(
            dealership=self.dealer, stock_number='RECON-OLD-VEH', year=2019, make='Synthetic', model='Aged',
            acquired_on=today - timedelta(days=40),
        )
        overdue_task = self.task(title='Overdue brake job', due_on=today - timedelta(days=3))
        today_task = self.task(title='Today oil service', due_on=today)
        upcoming_task = self.task(title='Upcoming detail', due_on=today + timedelta(days=4))
        unscheduled_task = add_task(
            vehicle_id=old_vehicle.pk, dealership=self.dealer, actor=self.user,
            data={'title': 'Unscheduled trim check', 'request_key': uuid4(), 'new_vendor': ''},
        )
        done_past_task = self.task(title='Completed past task', due_on=today - timedelta(days=5))
        change_task(vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user, task_id=done_past_task.pk, revision=1, status='done')
        ReconTask.objects.create(vehicle=self.foreign, title='Foreign overdue', due_on=today - timedelta(days=3), created_by=self.user)

        # Backdate created_at for aging buckets
        ReconTask.objects.filter(pk=overdue_task.pk).update(created_at=now - timedelta(days=10))
        ReconTask.objects.filter(pk=upcoming_task.pk).update(created_at=now - timedelta(days=20))
        ReconTask.objects.filter(pk=unscheduled_task.pk).update(created_at=now - timedelta(days=35))

        url = reverse('recon_queue')
        # Schedule filters
        self.assertEqual([t.pk for t in self.client.get(url, {'schedule': 'overdue'}).context['work']], [overdue_task.pk])
        self.assertEqual([t.pk for t in self.client.get(url, {'scope': 'all', 'schedule': 'overdue'}).context['work']], [overdue_task.pk])
        self.assertEqual([t.pk for t in self.client.get(url, {'schedule': 'today'}).context['work']], [today_task.pk])
        self.assertEqual([t.pk for t in self.client.get(url, {'schedule': 'upcoming'}).context['work']], [upcoming_task.pk])
        self.assertEqual([t.pk for t in self.client.get(url, {'schedule': 'unscheduled'}).context['work']], [unscheduled_task.pk])

        # Task age buckets
        self.assertEqual([t.pk for t in self.client.get(url, {'age': '0_7'}).context['work']], [today_task.pk])
        self.assertEqual([t.pk for t in self.client.get(url, {'age': '8_14'}).context['work']], [overdue_task.pk])
        self.assertEqual([t.pk for t in self.client.get(url, {'age': '15_30'}).context['work']], [upcoming_task.pk])
        self.assertEqual([t.pk for t in self.client.get(url, {'age': 'over_30'}).context['work']], [unscheduled_task.pk])

        # Sort by earliest target date and oldest vehicle acquisition (unknown dates last)
        by_due = [t.pk for t in self.client.get(url, {'sort': 'due'}).context['work']]
        self.assertEqual(by_due, [overdue_task.pk, today_task.pk, upcoming_task.pk, unscheduled_task.pk])
        by_veh_acq = [t.pk for t in self.client.get(url, {'sort': 'vehicle_oldest'}).context['work']]
        self.assertEqual(by_veh_acq[0], unscheduled_task.pk)

        # Shared filter builder: vehicle_acquired date filter and unknown acquisition dates
        acq_filtered = self.client.get(url, {'filter_field': 'vehicle_acquired', 'filter_op': 'lte', 'filter_value': (today - timedelta(days=30)).isoformat()})
        self.assertEqual([t.pk for t in acq_filtered.context['work']], [unscheduled_task.pk])
        self.assertContains(self.client.get(url), 'Acquisition date not entered')
        self.assertContains(self.client.get(url), 'Operational work tracking only')

    def test_vendor_contacts_isolation_revision_audit_and_snapshot_preservation(self):
        viewer = get_user_model().objects.create_user(username='vendor-viewer')
        Membership.objects.create(user=viewer, dealership=self.dealer, role='viewer')
        foreign_staff = get_user_model().objects.create_user(username='vendor-foreign')
        Membership.objects.create(user=foreign_staff, dealership=self.other, role='staff')
        foreign_vendor = VehicleVendor.objects.create(
            dealership=self.other, name='Foreign Body Shop', normalized_name='foreign body shop',
            phone='555-9999', created_by=foreign_staff,
        )

        # Create vendor with contact details; duplicate retry is idempotent
        create_url = reverse('vendor_create')
        payload = {
            'request_key': str(uuid4()), 'name': '  Synthetic   Tire & Alignment ',
            'contact_name': 'Casey Shop', 'phone': '555-0144',
            'email': 'shop@example.invalid', 'address': '100 Practice Way',
            'notes': 'Call before drop-off',
        }
        self.assertEqual(self.client.post(create_url, payload).status_code, 302)
        self.assertEqual(self.client.post(create_url, payload).status_code, 302)
        self.assertEqual(VehicleVendor.objects.filter(dealership=self.dealer).count(), 1)
        vendor = VehicleVendor.objects.get(dealership=self.dealer)
        self.assertEqual(vendor.name, 'Synthetic Tire & Alignment')
        self.assertEqual(vendor.normalized_name, 'synthetic tire & alignment')
        self.assertEqual(vendor.contact_name, 'Casey Shop')
        self.assertEqual(VehicleVendorEvent.objects.filter(vendor=vendor, action='created').count(), 1)

        # Duplicate vendor name with different details is rejected without duplicating
        dup = self.client.post(create_url, payload | {'request_key': str(uuid4()), 'phone': '555-0000'})
        self.assertContains(dup, 'already exists')
        self.assertEqual(VehicleVendor.objects.filter(dealership=self.dealer).count(), 1)

        # Record a cost linked to this vendor, then rename/update vendor contacts
        entry = self.cost(self.data() | {'vendor': vendor, 'new_vendor': ''})
        self.assertEqual(entry.vendor_name, 'Synthetic Tire & Alignment')

        edit_url = reverse('vendor_edit', args=[vendor.pk])
        updated = self.client.post(edit_url, {
            'revision': 1, 'name': 'Synthetic Tire & Brake',
            'contact_name': 'Jordan Lead', 'phone': '555-0188',
            'email': 'brake@example.invalid', 'address': '200 Practice Blvd',
            'notes': 'Updated shop hours',
        })
        self.assertEqual(updated.status_code, 302)
        vendor.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual((vendor.name, vendor.contact_name, vendor.revision), ('Synthetic Tire & Brake', 'Jordan Lead', 2))
        # Historical cost snapshot remains unchanged
        self.assertEqual(entry.vendor_name, 'Synthetic Tire & Alignment')
        self.assertEqual(VehicleVendorEvent.objects.filter(vendor=vendor, action='updated').count(), 1)

        # Stale edit returns 409 and preserves user input
        stale = self.client.post(edit_url, {
            'revision': 1, 'name': 'Stale Vendor Name', 'contact_name': 'Stale Contact',
            'phone': '', 'email': '', 'address': '', 'notes': '',
        })
        self.assertContains(stale, 'Stale Vendor Name', status_code=409)
        vendor.refresh_from_db()
        self.assertEqual(vendor.name, 'Synthetic Tire & Brake')

        # Audit failure rolls back vendor edit
        with patch('inventory.reconditioning.VehicleVendorEvent.objects.create', side_effect=RuntimeError('vendor audit down')):
            with self.assertRaises(RuntimeError):
                save_vendor(dealership=self.dealer, actor=self.user, vendor_id=vendor.pk, data={
                    'revision': 2, 'name': 'Rolled Back Vendor', 'contact_name': '',
                    'phone': '', 'email': '', 'address': '', 'notes': '',
                })
        vendor.refresh_from_db()
        self.assertEqual((vendor.name, vendor.revision), ('Synthetic Tire & Brake', 2))

        # Search in vendor list and isolation from foreign dealership
        list_res = self.client.get(reverse('vendor_list'), {'q': 'Jordan 555-0188'})
        self.assertEqual([v.pk for v in list_res.context['vendors']], [vendor.pk])
        self.assertNotContains(self.client.get(reverse('vendor_list')), 'Foreign Body Shop')
        self.assertEqual(self.client.get(reverse('vendor_detail', args=[foreign_vendor.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('vendor_edit', args=[foreign_vendor.pk])).status_code, 404)

        # Viewer can read vendor list and detail, but cannot create or edit
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(reverse('vendor_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('vendor_detail', args=[vendor.pk])).status_code, 200)
        self.assertEqual(self.client.get(create_url).status_code, 403)
        self.assertEqual(self.client.post(edit_url, {'revision': 2, 'name': 'Nope'}).status_code, 403)

    def test_queue_csv_export_all_pages_filters_isolation_and_formula_safety(self):
        import csv
        import io
        viewer = get_user_model().objects.create_user(username='queue-export-viewer')
        Membership.objects.create(user=viewer, dealership=self.dealer, role='viewer')
        today = timezone.localdate()

        # Create 30 matching tasks (more than 1 page of 25) plus a dangerous formula-like task and a foreign task
        for n in range(30):
            self.task(title=f'Batch job {n:02d}', due_on=today - timedelta(days=1))
        danger_vendor = VehicleVendor.objects.create(
            dealership=self.dealer, name='@VENDOR_CMD()', normalized_name='@vendor_cmd()', created_by=self.user,
        )
        danger_task = add_task(
            vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user,
            data={
                'title': '=CMD()', 'detail': '+SUM(1,2)', 'vendor': danger_vendor,
                'new_vendor': '', 'assigned_to': self.user, 'due_on': None, 'request_key': uuid4(),
            },
        )
        ReconTask.objects.create(vehicle=self.foreign, title='Foreign secret task', due_on=today - timedelta(days=1), created_by=self.user)

        export_url = reverse('recon_queue_export')
        # Viewer can export; all 31 open tasks are exported across pages
        self.client.force_login(viewer)
        res = self.client.get(export_url, {'scope': 'open', 'sort': 'due', 'page': '2'})
        self.assertEqual(res.status_code, 200)
        self.assertIn('no-store', res['Cache-Control'])
        self.assertEqual(res['Content-Security-Policy'], 'sandbox')
        self.assertIn('DEMO-reconditioning-work-open.csv', res['Content-Disposition'])
        self.assertEqual(self.client.head(export_url).status_code, 200)
        self.assertEqual(self.client.post(export_url).status_code, 405)

        text = res.content.decode('utf-8-sig')
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(rows), 31)
        self.assertNotIn('Foreign secret task', text)

        # Last row (null due_on sorted last) has formula cells escaped and explicit unscheduled status
        last = rows[-1]
        self.assertEqual(last['task_id'], str(danger_task.pk))
        self.assertEqual(last['title'], "'=CMD()")
        self.assertEqual(last['detail'], "'+SUM(1,2)")
        self.assertEqual(last['vendor_name'], "'@VENDOR_CMD()")
        self.assertEqual(last['target_date'], '')
        self.assertEqual(last['target_status'], 'unscheduled')
        self.assertIn('operational reconditioning work tracking', last['report_note'])

        # Schedule filter (overdue) excludes unscheduled task and exports only the 30 overdue tasks
        overdue_res = self.client.get(export_url, {'schedule': 'overdue'})
        overdue_rows = list(csv.DictReader(io.StringIO(overdue_res.content.decode('utf-8-sig'))))
        self.assertEqual(len(overdue_rows), 30)
        self.assertEqual(overdue_rows[0]['target_status'], 'overdue')

        # Invalid filter state returns 400 rather than exporting unfiltered data
        self.assertEqual(self.client.get(export_url, {'scope': 'invalid-scope'}).status_code, 400)
        with override_settings(RECON_DEMO_ENABLED=False):
            self.assertEqual(self.client.get(export_url).status_code, 404)

    def test_vehicle_cost_csv_export_all_pages_reversals_isolation_and_formula_safety(self):
        import csv
        import io
        viewer = get_user_model().objects.create_user(username='cost-export-viewer')
        Membership.objects.create(user=viewer, dealership=self.dealer, role='viewer')
        foreign_staff = get_user_model().objects.create_user(username='cost-export-foreign')
        Membership.objects.create(user=foreign_staff, dealership=self.other, role='staff')

        # Foreign vehicle cost must never appear or be accessible
        add_cost(
            vehicle_id=self.foreign.pk, dealership=self.other, actor=foreign_staff,
            data=self.data() | {'description': 'Foreign secret cost'},
        )

        # Create 28 costs on self.vehicle (more than 1 page of 25), reverse one with a formula-like reason, and add a formula-like cost
        for n in range(28):
            self.cost(self.data() | {'description': f'Batch cost {n:02d}', 'amount': Decimal('10.00')})
        danger_task = self.task(title='=TASK_FORMULA()', new_vendor='')
        danger_cost = self.cost(self.data() | {
            'description': '=CMD_COST()', 'amount': Decimal('250.35'),
            'new_vendor': '+VENDOR_FORMULA()', 'task': danger_task,
        })
        reversal = reverse_cost(
            vehicle_id=self.vehicle.pk, dealership=self.dealer, actor=self.user,
            entry_id=danger_cost.pk, reason='@REVERSAL_FORMULA()', request_key=uuid4(),
        )

        url = reverse('vehicle_recon', args=[self.vehicle.pk])
        # Workspace page links to the export
        self.assertContains(self.client.get(url), f'{url}?export=costs')

        # Cross-dealership vehicle returns 404
        self.assertEqual(self.client.get(reverse('vehicle_recon', args=[self.foreign.pk]), {'export': 'costs'}).status_code, 404)

        # Viewer can export all 30 entries (28 batch + 1 danger_cost + 1 reversal) regardless of page param
        self.client.force_login(viewer)
        res = self.client.get(url, {'export': 'costs', 'page': '2'})
        self.assertEqual(res.status_code, 200)
        self.assertIn('no-store', res['Cache-Control'])
        self.assertEqual(res['Content-Security-Policy'], 'sandbox')
        self.assertIn(f'DEMO-vehicle-{self.vehicle.pk}-costs.csv', res['Content-Disposition'])
        self.assertEqual(self.client.head(url, {'export': 'costs'}).status_code, 200)
        self.assertEqual(self.client.post(url + '?export=costs').status_code, 405)

        text = res.content.decode('utf-8-sig')
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(rows), 30)
        self.assertNotIn('Foreign secret cost', text)

        # Newest entry is the reversal; second newest is the original danger_cost
        rev_row = rows[0]
        orig_row = rows[1]
        self.assertEqual(rev_row['entry_id'], str(reversal.pk))
        self.assertEqual(rev_row['kind'], 'reversal')
        self.assertEqual(rev_row['reverses_entry_id'], str(danger_cost.pk))
        self.assertEqual(rev_row['signed_amount_usd'], "'-250.35")
        self.assertEqual(rev_row['amount_cents'], "'-25035")
        self.assertEqual(rev_row['debit'], 'cost_offset')
        self.assertEqual(rev_row['credit'], 'vehicle_cost')
        self.assertEqual(rev_row['correction_reason'], "'@REVERSAL_FORMULA()")
        self.assertEqual(rev_row['description'], "'=CMD_COST()")
        self.assertEqual(rev_row['vendor_snapshot_name'], "'+VENDOR_FORMULA()")
        self.assertEqual(rev_row['task_title'], "'=TASK_FORMULA()")

        self.assertEqual(orig_row['entry_id'], str(danger_cost.pk))
        self.assertEqual(orig_row['kind'], 'cost')
        self.assertEqual(orig_row['reversed_by_entry_id'], str(reversal.pk))
        self.assertEqual(orig_row['signed_amount_usd'], '250.35')
        # Net itemized is 28 * 10.00 = 280.00; total recorded investment is 5000.10 + 100.20 + 280.00 = 5380.30
        self.assertEqual(orig_row['net_itemized_cost_usd'], '280.00')
        self.assertEqual(orig_row['total_recorded_investment_usd'], '5380.30')
        self.assertIn('not accounts payable', orig_row['report_note'])

        with override_settings(RECON_DEMO_ENABLED=False):
            self.assertEqual(self.client.get(url, {'export': 'costs'}).status_code, 404)

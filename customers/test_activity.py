# SPDX-License-Identifier: MPL-2.0
from unittest.mock import patch
from importlib import import_module
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from core.models import Dealership, Membership
from .models import Customer, CustomerActivity, CustomerEvent


@override_settings(CUSTOMER_ACTIVITY_DEMO_ENABLED=True)
class CustomerActivityTests(TestCase):
    def setUp(self):
        self.dealer=Dealership.objects.create(name='Synthetic CRM')
        self.other=Dealership.objects.create(name='Other synthetic CRM')
        self.staff=get_user_model().objects.create_user('crm-staff')
        self.viewer=get_user_model().objects.create_user('crm-viewer')
        Membership.objects.create(user=self.staff,dealership=self.dealer,role='staff')
        Membership.objects.create(user=self.viewer,dealership=self.dealer,role='viewer')
        self.customer=Customer.objects.create(dealership=self.dealer,first_name='Practice',last_name='Buyer')
        self.foreign=Customer.objects.create(dealership=self.other,first_name='Other',last_name='Buyer')
        self.client.force_login(self.staff)
        self.url=reverse('customer_activity_create',args=[self.customer.pk])
        self.data={'kind':'follow_up','detail':'Practice callback','creation_key':str(uuid4())}

    def test_create_retry_completion_and_audit(self):
        self.assertEqual(self.client.post(self.url,self.data).status_code,302)
        self.assertEqual(self.client.post(self.url,self.data).status_code,302)
        activity=CustomerActivity.objects.get(customer=self.customer)
        self.assertEqual(CustomerEvent.objects.count(),1)
        response=self.client.post(reverse('customer_activity_complete',args=[self.customer.pk,activity.pk]),{'revision':activity.revision})
        self.assertEqual(response.status_code,302)
        activity.refresh_from_db()
        self.client.post(reverse('customer_activity_complete',args=[self.customer.pk,activity.pk]),{'revision':activity.revision})
        activity.refresh_from_db();self.assertEqual(activity.completed_by,self.staff)
        self.assertEqual(CustomerEvent.objects.count(),2)
        response=self.client.get(reverse('customer_detail',args=[self.customer.pk]))
        self.assertContains(response,'Practice callback')
        self.assertContains(response,'Completed activity #')
        self.assertContains(response,'Added follow-up')

    def test_customer_events_reject_database_update_and_delete(self):
        if connection.vendor not in ('sqlite', 'postgresql'):
            self.skipTest('Customer event guards support SQLite and PostgreSQL.')
        self.assertEqual(self.client.post(self.url, self.data).status_code, 302)
        activity = CustomerActivity.objects.get(customer=self.customer)
        self.assertEqual(self.client.post(reverse('customer_activity_complete', args=[self.customer.pk, activity.pk]), {'revision': 1}).status_code, 302)
        events = list(CustomerEvent.objects.filter(customer=self.customer).order_by('pk').values())
        self.assertEqual([row['changes']['action'] for row in events], ['activity_created', 'activity_completed'])
        event_id = events[0]['id']

        def raw(sql):
            with connection.cursor() as cursor:
                cursor.execute(sql, [event_id])

        operations = (
            lambda: CustomerEvent.objects.filter(pk=event_id).update(changes={'synthetic': 'changed'}),
            lambda: CustomerEvent.objects.filter(pk=event_id).delete(),
            lambda: raw("UPDATE customers_customerevent SET changes = '{}' WHERE id = %s"),
            lambda: raw('DELETE FROM customers_customerevent WHERE id = %s'),
        )
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaisesRegex(DatabaseError, 'Customer events are immutable'), transaction.atomic():
                operation()
        self.assertEqual(list(CustomerEvent.objects.filter(customer=self.customer).order_by('pk').values()), events)
        self.assertEqual(self.client.get(reverse('customer_detail', args=[self.customer.pk])).status_code, 200)

    def test_customer_event_guard_migration_reverses_and_reapplies_without_losing_rows(self):
        if connection.vendor not in ('sqlite', 'postgresql'):
            self.skipTest('Customer event guards support SQLite and PostgreSQL.')
        self.assertEqual(self.client.post(self.url, self.data).status_code, 302)
        event = CustomerEvent.objects.get(customer=self.customer)
        migration = import_module('customers.migrations.0010_customer_event_immutable')

        class Editor:
            def __init__(self, db):
                self.connection = db

            def execute(self, sql):
                with self.connection.cursor() as cursor:
                    cursor.execute(sql)

        editor = Editor(connection)
        migration.backward(None, editor)
        try:
            self.assertEqual(CustomerEvent.objects.filter(pk=event.pk).update(changes={'synthetic': 'retained'}), 1)
        finally:
            migration.forward(None, editor)
        self.assertEqual(CustomerEvent.objects.get(pk=event.pk).changes, {'synthetic': 'retained'})
        with self.assertRaisesRegex(DatabaseError, 'Customer events are immutable'), transaction.atomic():
            CustomerEvent.objects.filter(pk=event.pk).delete()

    def test_actor_revoked_after_request_checks_cannot_mutate_or_retry(self):
        from .activity import _require_locked_editor
        self.client.post(self.url, self.data)
        activity = CustomerActivity.objects.get(customer=self.customer)
        edit = reverse('customer_activity_edit', args=[self.customer.pk, activity.pk])
        complete = reverse('customer_activity_complete', args=[self.customer.pk, activity.pk])
        requests = [(self.url, self.data),
                    (edit, {'detail': activity.detail, 'due_at': '', 'assigned_to': '', 'revision': 1}),
                    (complete, {'revision': 1})]
        for revoked in ('inactive', 'viewer', 'foreign', 'removed'):
            for url, data in requests:
                with self.subTest(revoked=revoked, url=url):
                    def revoke(user, dealership_id):
                        if revoked == 'inactive':
                            get_user_model().objects.filter(pk=user.pk).update(is_active=False)
                        elif revoked == 'removed':
                            Membership.objects.filter(user=user).delete()
                        elif revoked == 'viewer':
                            Membership.objects.filter(user=user).update(role='viewer')
                        else:
                            Membership.objects.filter(user=user).update(dealership=self.other)
                        return _require_locked_editor(user, dealership_id)
                    with patch('customers.activity._require_locked_editor', side_effect=revoke):
                        self.assertEqual(self.client.post(url, data).status_code, 403)
                    self.assertEqual(CustomerActivity.objects.count(), 1)
                    self.assertEqual(CustomerEvent.objects.count(), 1)
                    activity.refresh_from_db()
                    self.assertEqual((activity.revision, activity.completed_at, activity.detail), (1, None, 'Practice callback'))

    def test_assignee_revoked_after_form_validation_cannot_be_assigned_or_retried(self):
        from .activity import _locked_editor
        assignee = get_user_model().objects.create_user('synthetic-activity-assignee')
        Membership.objects.create(user=assignee, dealership=self.dealer, role='staff')
        data = self.data | {'assigned_to': assignee.pk}
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        activity = CustomerActivity.objects.get(customer=self.customer)
        edit = reverse('customer_activity_edit', args=[self.customer.pk, activity.pk])
        for revoked in ('inactive', 'viewer', 'foreign', 'removed'):
            for url, payload in ((self.url, data), (edit, {'detail': activity.detail, 'due_at': '', 'assigned_to': assignee.pk, 'revision': 1})):
                with self.subTest(revoked=revoked, url=url):
                    def revoke(user, dealership_id):
                        if user.pk == assignee.pk:
                            if revoked == 'inactive':
                                get_user_model().objects.filter(pk=user.pk).update(is_active=False)
                            elif revoked == 'removed':
                                Membership.objects.filter(user=user).delete()
                            elif revoked == 'viewer':
                                Membership.objects.filter(user=user).update(role='viewer')
                            else:
                                Membership.objects.filter(user=user).update(dealership=self.other)
                        return _locked_editor(user, dealership_id)
                    with patch('customers.activity._locked_editor', side_effect=revoke):
                        self.assertEqual(self.client.post(url, payload).status_code, 409)
                    self.assertEqual(CustomerActivity.objects.count(), 1)
                    self.assertEqual(CustomerEvent.objects.count(), 1)
                    get_user_model().objects.filter(pk=assignee.pk).update(is_active=True)
                    Membership.objects.update_or_create(user=assignee, defaults={'dealership': self.dealer, 'role': 'staff'})
    def test_permissions_isolation_csrf_and_gate(self):
        self.assertEqual(self.client.post(reverse('customer_activity_create',args=[self.foreign.pk]),self.data).status_code,404)
        self.client.force_login(self.viewer);self.assertEqual(self.client.post(self.url,self.data).status_code,403)
        client=Client(enforce_csrf_checks=True);client.force_login(self.staff);self.assertEqual(client.post(self.url,self.data).status_code,403)
        self.client.force_login(self.staff)
        with override_settings(CUSTOMER_ACTIVITY_DEMO_ENABLED=False):self.assertEqual(self.client.get(self.url).status_code,404)

    def test_audit_failure_rolls_back_and_conflicting_retry_rejected(self):
        with patch('customers.activity.CustomerEvent.objects.create',side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):self.client.post(self.url,self.data)
        self.assertFalse(CustomerActivity.objects.exists())
        self.client.post(self.url,self.data)
        response=self.client.post(self.url,self.data|{'detail':'Different'})
        self.assertContains(response,'already used for another activity')
        self.assertEqual(CustomerActivity.objects.count(),1)

    def test_note_with_due_date_is_rejected_and_input_preserved(self):
        response=self.client.post(self.url,self.data|{'kind':'note','due_at':'2026-11-01T10:00'})
        self.assertContains(response,'Dates belong to follow-ups')
        self.assertContains(response,'Practice callback')
        self.assertFalse(CustomerActivity.objects.exists())

    def test_queue_scopes_search_and_status(self):
        self.client.post(self.url,self.data)
        own=CustomerActivity.objects.get(customer=self.customer)
        CustomerActivity.objects.create(customer=self.foreign,kind='appointment',detail='Private appointment',created_by=self.staff,creation_key=uuid4())
        queue=reverse('customer_activity_queue')
        response=self.client.get(queue,{'q':'Practice Buyer'})
        self.assertEqual([item.pk for item in response.context['activities']],[own.pk])
        self.assertNotContains(response,'Private appointment')
        self.assertIn('no-store',response['Cache-Control'])
        self.client.post(reverse('customer_activity_complete',args=[self.customer.pk,own.pk]),{'revision':own.revision})
        self.assertEqual(self.client.get(queue).context['page_obj'].paginator.count,0)
        self.assertEqual(self.client.get(queue,{'status':'done'}).context['page_obj'].paginator.count,1)
        with override_settings(CUSTOMER_ACTIVITY_DEMO_ENABLED=False):self.assertEqual(self.client.get(queue).status_code,404)

    def test_queue_completion_preserves_filters_without_open_redirect(self):
        self.client.post(self.url,self.data)
        activity=CustomerActivity.objects.get(customer=self.customer)
        response=self.client.post(reverse('customer_activity_complete',args=[self.customer.pk,activity.pk]),{'return_to':'queue','status':'open','q':'Practice','page':'1','revision':activity.revision})
        self.assertRedirects(response,reverse('customer_activity_queue')+'?status=open&q=Practice&page=1')
        activity.refresh_from_db();self.assertIsNotNone(activity.completed_at)

    def test_assignment_reschedule_reopen_and_history(self):
        self.data['assigned_to']=self.staff.pk
        self.client.post(self.url,self.data)
        activity=CustomerActivity.objects.get(customer=self.customer)
        self.assertEqual(activity.assigned_to,self.staff)
        edit=reverse('customer_activity_edit',args=[self.customer.pk,activity.pk])
        response=self.client.post(edit,{'detail':'Rescheduled practice call','due_at':'2026-11-15T14:30','assigned_to':'','revision':activity.revision})
        self.assertEqual(response.status_code,302)
        activity.refresh_from_db();self.assertIsNone(activity.assigned_to);self.assertEqual(activity.revision,2)
        self.assertEqual(CustomerEvent.objects.filter(changes__action='activity_updated').count(),1)
        complete=reverse('customer_activity_complete',args=[self.customer.pk,activity.pk])
        self.assertEqual(self.client.post(complete,{'revision':2}).status_code,302)
        self.assertEqual(self.client.post(complete,{'revision':2,'action':'reopen'}).status_code,409)
        activity.refresh_from_db();self.assertIsNotNone(activity.completed_at)
        self.assertEqual(self.client.post(complete,{'revision':activity.revision,'action':'reopen'}).status_code,302)
        activity.refresh_from_db();self.assertIsNone(activity.completed_at);self.assertIsNone(activity.completed_by)
        self.assertEqual(CustomerEvent.objects.filter(changes__action='activity_reopened').count(),1)

    def test_stale_edits_preserve_input_and_foreign_assignee_rejected(self):
        foreign_user=get_user_model().objects.create_user('foreign-assignee')
        Membership.objects.create(user=foreign_user,dealership=self.other,role='staff')
        self.client.post(self.url,self.data)
        activity=CustomerActivity.objects.get(customer=self.customer)
        edit=reverse('customer_activity_edit',args=[self.customer.pk,activity.pk])
        invalid=self.client.post(edit,{'detail':'Keep this entry','due_at':'','assigned_to':foreign_user.pk,'revision':1})
        self.assertContains(invalid,'Select a valid choice');self.assertContains(invalid,'Keep this entry')
        self.client.post(edit,{'detail':'First edit','due_at':'','assigned_to':'','revision':1})
        stale=self.client.post(edit,{'detail':'Unsaved second edit','due_at':'','assigned_to':'','revision':1})
        self.assertContains(stale,'Unsaved second edit',status_code=409)
        activity.refresh_from_db();self.assertEqual(activity.detail,'First edit')
        self.client.force_login(self.viewer);self.assertEqual(self.client.get(edit).status_code,403)

    def test_edit_audit_failure_rolls_back(self):
        self.client.post(self.url,self.data);activity=CustomerActivity.objects.get(customer=self.customer)
        with patch('customers.activity.CustomerEvent.objects.create',side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):self.client.post(reverse('customer_activity_edit',args=[self.customer.pk,activity.pk]),{'detail':'Changed','due_at':'','assigned_to':'','revision':1})
        activity.refresh_from_db();self.assertEqual((activity.detail,activity.revision),('Practice callback',1))

    def test_full_customer_activity_history_is_paginated_and_scoped(self):
        for n in range(30):
            CustomerActivity.objects.create(customer=self.customer,kind='note',detail=f'Practice note {n}',created_by=self.staff,creation_key=uuid4())
        route=reverse('customer_activity_history',args=[self.customer.pk])
        response=self.client.get(route)
        self.assertEqual(response.context['page_obj'].paginator.count,30)
        self.assertEqual(len(response.context['activities']),25)
        self.assertEqual(len(self.client.get(route,{'page':2}).context['activities']),5)
        self.assertEqual(self.client.get(reverse('customer_activity_history',args=[self.foreign.pk])).status_code,404)
        self.assertContains(self.client.get(reverse('customer_detail',args=[self.customer.pk])),'View all customer activity')

    def test_queue_and_history_richer_search_and_deal_handoffs(self):
        from inventory.models import Vehicle
        from deals.models import DraftDeal
        self.customer.phone='(555) 234-5678'
        self.customer.email='practice.buyer@example.invalid'
        self.customer.save()
        assignee=get_user_model().objects.create_user('crm-assignee')
        Membership.objects.create(user=assignee,dealership=self.dealer,role='staff')
        follow_up=CustomerActivity.objects.create(
            customer=self.customer,kind='follow_up',detail='Discuss trade-in numbers',
            created_by=self.staff,assigned_to=assignee,creation_key=uuid4(),
        )
        note=CustomerActivity.objects.create(
            customer=self.customer,kind='note',detail='Walk-in conversation note',
            created_by=self.staff,creation_key=uuid4(),
        )
        foreign_vehicle=Vehicle.objects.create(dealership=self.other,stock_number='FOREIGN-DEAL',year=2020,make='Other',model='Car')
        foreign_deal=DraftDeal.objects.create(dealership=self.other,vehicle=foreign_vehicle,buyer=self.foreign)

        queue_url=reverse('customer_activity_queue')
        # Before a deal exists, staff see Start a deal link; viewers do not
        q_res=self.client.get(queue_url)
        self.assertContains(q_res,f'{reverse("deal_create")}?buyer={self.customer.pk}')
        self.client.force_login(self.viewer)
        self.assertNotContains(self.client.get(queue_url),reverse('deal_create'))
        self.client.force_login(self.staff)

        # Create a local deal for this customer and verify direct handoff in queue and history
        local_vehicle=Vehicle.objects.create(dealership=self.dealer,stock_number='LOCAL-DEAL',year=2021,make='Synthetic',model='Coupe')
        local_deal=DraftDeal.objects.create(dealership=self.dealer,vehicle=local_vehicle,buyer=self.customer)
        q_res=self.client.get(queue_url)
        self.assertContains(q_res,reverse('deal_detail',args=[local_deal.pk]))
        self.assertContains(q_res,f'Deal #{local_deal.pk}')
        self.assertNotContains(q_res,f'Deal #{foreign_deal.pk}')

        # Queue search by phone, email, and assignee username
        for q in ['555-234-5678','2345678','practice.buyer@example.invalid','crm-assignee','Discuss crm-assignee']:
            res=self.client.get(queue_url,{'q':q})
            self.assertEqual([item.pk for item in res.context['activities']],[follow_up.pk])

        # History search by detail/assignee, filter by kind, and deal handoff links
        hist_url=reverse('customer_activity_history',args=[self.customer.pk])
        hist_res=self.client.get(hist_url)
        self.assertContains(hist_res,reverse('deal_detail',args=[local_deal.pk]))
        self.assertContains(hist_res,f'{reverse("deal_create")}?buyer={self.customer.pk}')
        self.assertEqual([a.pk for a in self.client.get(hist_url,{'kind':'note'}).context['activities']],[note.pk])
        self.assertEqual([a.pk for a in self.client.get(hist_url,{'q':'crm-assignee'}).context['activities']],[follow_up.pk])
        self.assertEqual([a.pk for a in self.client.get(hist_url,{'q':'Walk-in'}).context['activities']],[note.pk])


@override_settings(CUSTOMER_ACTIVITY_DEMO_ENABLED=True)
class CustomerActivityAuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealership.objects.create(name='Synthetic local')
        cls.other = Dealership.objects.create(name='Synthetic foreign')
        cls.users = {}
        for role, dealer in [('owner', cls.dealer), ('staff', cls.dealer), ('viewer', cls.dealer), ('foreign', cls.other)]:
            user = get_user_model().objects.create_user('activity-' + role)
            Membership.objects.create(user=user, dealership=dealer, role='owner' if role == 'foreign' else role)
            cls.users[role] = user
        cls.customer = Customer.objects.create(dealership=cls.dealer, first_name='Synthetic', last_name='Local')
        cls.foreign = Customer.objects.create(dealership=cls.other, first_name='Synthetic', last_name='Foreign')
        cls.activity = CustomerActivity.objects.create(customer=cls.customer, kind='follow_up', detail='Local private task', created_by=cls.users['staff'], creation_key=uuid4())
        cls.foreign_activity = CustomerActivity.objects.create(customer=cls.foreign, kind='follow_up', detail='Foreign private task', created_by=cls.users['foreign'], creation_key=uuid4())

    def urls(self, customer, activity):
        return {
            'queue': reverse('customer_activity_queue'),
            'history': reverse('customer_activity_history', args=[customer.pk]),
            'create': reverse('customer_activity_create', args=[customer.pk]),
            'edit': reverse('customer_activity_edit', args=[customer.pk, activity.pk]),
            'complete': reverse('customer_activity_complete', args=[customer.pk, activity.pk]),
        }

    def test_direct_urls_and_cross_customer_ids(self):
        urls = self.urls(self.customer, self.activity)
        for url in urls.values():
            self.assertEqual(self.client.get(url).status_code, 302)
        for role in ('viewer', 'staff', 'owner', 'foreign'):
            with self.subTest(role=role):
                self.client.force_login(self.users[role])
                self.assertEqual(self.client.get(urls['queue']).status_code, 200)
                local = role != 'foreign'
                self.assertEqual(self.client.get(urls['history']).status_code, 200 if local else 404)
                expected = 403 if role == 'viewer' else 200 if local else 404
                self.assertEqual(self.client.get(urls['create']).status_code, expected)
                self.assertEqual(self.client.get(urls['edit']).status_code, expected)
                self.assertEqual(self.client.post(urls['complete'], {'revision': 1}).status_code, 403 if role == 'viewer' else 302 if local else 404)
                self.activity.refresh_from_db()
                if local and role in ('staff', 'owner'):
                    self.activity.completed_at = None
                    self.activity.completed_by = None
                    self.activity.revision = 1
                    self.activity.save(update_fields=['completed_at', 'completed_by', 'revision'])
                queue = self.client.get(urls['queue'])
                self.assertNotContains(queue, 'Foreign private task' if local else 'Local private task')
        self.client.force_login(self.users['owner'])
        mismatch = self.urls(self.customer, self.foreign_activity)
        self.assertEqual(self.client.get(mismatch['edit']).status_code, 404)
        self.assertEqual(self.client.post(mismatch['complete'], {'revision': 1}).status_code, 404)
        self.foreign_activity.refresh_from_db()
        self.assertIsNone(self.foreign_activity.completed_at)

    def test_mutation_roles_foreign_scope_and_stale_revision(self):
        urls = self.urls(self.customer, self.activity)
        create_data = {'kind': 'follow_up', 'detail': 'New synthetic task', 'creation_key': str(uuid4())}
        edit_data = {'detail': 'Synthetic edit', 'revision': 1, 'assigned_to': '', 'due_at': ''}
        for role, expected in [('viewer', 403), ('foreign', 404)]:
            self.client.force_login(self.users[role])
            for name, data in [('create', create_data), ('edit', edit_data), ('complete', {'revision': 1})]:
                self.assertEqual(self.client.post(urls[name], data).status_code, expected)
        self.assertEqual(CustomerActivity.objects.filter(customer=self.customer).count(), 1)
        for role in ('staff', 'owner'):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.post(urls['create'], create_data | {'creation_key': str(uuid4())}).status_code, 302)
        self.assertEqual(self.client.post(urls['edit'], edit_data).status_code, 302)
        self.assertEqual(self.client.post(urls['edit'], edit_data | {'detail': 'Stale change'}).status_code, 409)
        self.assertEqual(self.client.post(urls['complete'], {'revision': 1}).status_code, 409)
        self.activity.refresh_from_db()
        self.assertEqual((self.activity.detail, self.activity.revision, self.activity.completed_at), ('Synthetic edit', 2, None))

    def test_form_assignment_is_dealership_and_role_scoped(self):
        from .activity import ActivityForm, EditActivityForm
        for form_class in (ActivityForm, EditActivityForm):
            form = form_class(dealership=self.dealer)
            self.assertEqual(set(form.fields['assigned_to'].queryset.values_list('pk', flat=True)), {self.users['owner'].pk, self.users['staff'].pk})

    def test_anonymous_posts_and_archived_deal_do_not_change_activity_scope(self):
        from inventory.models import Vehicle
        from deals.models import DraftDeal
        from django.utils import timezone
        urls = self.urls(self.customer, self.activity)
        for name in ('create', 'edit', 'complete'):
            self.assertEqual(self.client.post(urls[name], {'revision': 1}).status_code, 302)
        vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='SYN-ARCHIVE', year=2020, make='Synthetic', model='Car')
        DraftDeal.objects.create(dealership=self.dealer, vehicle=vehicle, buyer=self.customer, archived_at=timezone.now(), archived_by=self.users['owner'])
        self.client.force_login(self.users['staff'])
        self.assertContains(self.client.get(urls['history']), 'Local private task')
        self.assertEqual(self.client.post(urls['complete'], {'revision': 1}).status_code, 302)
        self.activity.refresh_from_db()
        self.assertIsNotNone(self.activity.completed_at)
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(urls['history']).status_code, 404)

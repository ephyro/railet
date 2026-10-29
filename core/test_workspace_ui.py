# SPDX-License-Identifier: MPL-2.0
from django.contrib.auth import get_user_model
from django.test import TestCase,override_settings
from django.urls import reverse
from inventory.models import Vehicle
from customers.models import Customer
from deals.models import DraftDeal
from .models import Dealership,Membership


@override_settings(DEMO_LEDGER_ENABLED=True)
class WorkspaceNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer=Dealership.objects.create(name='Synthetic usability dealer')
        cls.users={}
        for name,role in [('staff','staff'),('viewer','viewer')]:
            user=get_user_model().objects.create_user('workspace-'+name)
            Membership.objects.create(user=user,dealership=cls.dealer,role=role);cls.users[name]=user
        cls.customer=Customer.objects.create(dealership=cls.dealer,first_name='Riley',last_name='Demo')
        cls.vehicle=Vehicle.objects.create(dealership=cls.dealer,stock_number='UX-SYNTHETIC',year=2020,make='Synthetic',model='Sedan')
        cls.deal=DraftDeal.objects.create(dealership=cls.dealer,vehicle=cls.vehicle,buyer=cls.customer,sale_price='1000',tax='50',deal_type='bhph')

    def setUp(self):self.client.force_login(self.users['staff'])

    def test_home_uses_plain_navigation_and_real_task_links(self):
        response=self.client.get(reverse('today'))
        for label in ('Home','Vehicles','Customers','Deals','BHPH'):
            self.assertContains(response,'>'+label+'</a>')
        self.assertNotContains(response,'>Draft deals</a>')
        for route in ('deals','inventory','customers','ledger_demo_list'):
            self.assertContains(response,reverse(route))
        self.assertContains(response,'Test workspace')
        for route in ('deal_create','vehicle_create','customer_create'):
            self.assertNotContains(response,reverse(route))

    def test_viewers_receive_browse_actions_without_creation_links(self):
        self.client.force_login(self.users['viewer']);response=self.client.get(reverse('today'))
        for route in ('deal_create','vehicle_create','customer_create'):
            self.assertNotContains(response,reverse(route))
        self.assertContains(response,'View vehicles')
        self.assertContains(response,'View customers')
        self.assertEqual(self.client.get(reverse('deal_create')).status_code,403)

    def test_payment_tasks_stay_hidden_when_demo_feature_is_disabled(self):
        with override_settings(DEMO_LEDGER_ENABLED=False):
            response=self.client.get(reverse('today'))
            self.assertNotContains(response,'>BHPH</a>')
            self.assertNotContains(response,'Record a payment')

    def test_deal_status_tabs_preserve_search_and_filter_settings(self):
        response=self.client.get(reverse('deals'),{'q':'Riley','filter_field':'type','filter_op':'eq','filter_value':'bhph'})
        for tab in response.context['deal_tabs']:
            self.assertIn('q=Riley',tab['query']);self.assertIn('filter_value=bhph',tab['query'])
        self.assertEqual(response.context['page_obj'].paginator.count,1)

    def test_new_deal_still_keeps_unknown_type_and_validation_feedback(self):
        response=self.client.get(reverse('deal_create'))
        self.assertEqual(response.context['form']['deal_type'].value(),'undecided')
        self.assertContains(response,'class="desk-type"')
        self.assertContains(response,'Price and payments')
        posted={'deal_type':'invented','vehicle':self.vehicle.pk,'customer_mode':'existing','buyer':self.customer.pk,'submission_key':str(response.context['form']['submission_key'].value())}
        response=self.client.post(reverse('deal_create'),posted)
        self.assertTrue(response.context['form']['deal_type'].errors)
        self.assertEqual(DraftDeal.objects.count(),1)

    def test_existing_amounts_and_inactive_forms_remain_in_disclosures(self):
        response=self.client.get(reverse('deal_detail',args=[self.deal.pk]))
        self.assertFalse(response.context['fees_open'])
        self.assertContains(response,'value="50')
        self.assertContains(response,'name="bhph-included"')
        self.assertContains(response,'Financing details')
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.tax,50)

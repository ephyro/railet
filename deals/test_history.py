# SPDX-License-Identifier: MPL-2.0
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from core.models import Dealership, Membership
from customers.models import Customer
from inventory.models import Vehicle
from .models import DraftDeal, DealEvent


class DraftHistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer=Dealership.objects.create(name='Synthetic history dealer')
        cls.other=Dealership.objects.create(name='Other dealer')
        cls.viewer=get_user_model().objects.create_user('history-viewer')
        cls.foreign=get_user_model().objects.create_user('history-foreign')
        Membership.objects.create(user=cls.viewer,dealership=cls.dealer,role='viewer')
        Membership.objects.create(user=cls.foreign,dealership=cls.other,role='owner')
        vehicle=Vehicle.objects.create(dealership=cls.dealer,stock_number='DEMO-HISTORY',year=2020,make='Synthetic',model='Sedan')
        buyer=Customer.objects.create(dealership=cls.dealer,first_name='Riley',last_name='Demo')
        cls.deal=DraftDeal.objects.create(dealership=cls.dealer,vehicle=vehicle,buyer=buyer)
        for n in range(27):
            DealEvent.objects.create(deal=cls.deal,actor=cls.viewer,snapshot={'schema_version':3,'revision':n+1,'action':'draft_saved','sale_price':'1234.50','reason':f'Synthetic entry {n+1}'})

    def setUp(self):
        self.client.force_login(self.viewer)
        self.url=reverse('deal_history',args=[self.deal.pk])

    def test_pagination_preserves_access_to_oldest_entries(self):
        first=self.client.get(self.url);second=self.client.get(self.url,{'page':2})
        self.assertEqual(len(first.context['rows']),25)
        self.assertEqual(len(second.context['rows']),2)
        self.assertEqual(second.context['rows'][-1]['saved']['revision'],1)
        self.assertContains(first,'$1,234.50')
        self.assertContains(second,'Synthetic entry 1')

    def test_role_scope_methods_and_cache(self):
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.assertIn('no-store',self.client.get(self.url)['Cache-Control'])
        self.assertEqual(self.client.post(self.url).status_code,405)
        self.client.force_login(self.foreign)
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.client.logout();self.assertEqual(self.client.get(self.url).status_code,302)

    def test_old_and_malformed_values_do_not_invent_current_facts(self):
        event=DealEvent.objects.create(deal=self.deal,actor=self.viewer,snapshot={'revision':28,'sale_price':'NaN','notes':'<script>Synthetic</script>'})
        original=event.snapshot.copy()
        response=self.client.get(self.url)
        self.assertEqual(response.context['rows'][0]['amounts'][0][1],'Not recorded in this version')
        self.assertContains(response,'&lt;script&gt;Synthetic&lt;/script&gt;')
        self.assertNotContains(response,'<script>Synthetic')
        event.refresh_from_db();self.assertEqual(event.snapshot,original)
        self.deal.refresh_from_db();self.assertEqual(self.deal.revision,1)

    def test_empty_and_invalid_pages_have_usable_results(self):
        self.assertEqual(self.client.get(self.url,{'page':'invalid'}).status_code,200)
        self.assertEqual(self.client.get(self.url,{'page':999}).context['page'].number,2)
        self.deal.events.all().delete()
        self.assertContains(self.client.get(self.url),'No saved history is available')

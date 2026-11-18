# SPDX-License-Identifier: MPL-2.0
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Dealership, Membership
from .models import Vehicle


@override_settings(DEBUG=True)
class DuplicateVINReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealership.objects.create(name='Synthetic report dealer')
        cls.other = Dealership.objects.create(name='Other synthetic dealer')
        cls.users = {}
        for role in ('owner', 'staff', 'viewer'):
            user = get_user_model().objects.create_user(f'vin-report-{role}')
            Membership.objects.create(user=user, dealership=cls.dealer, role=role)
            cls.users[role] = user
        cls.no_membership = get_user_model().objects.create_user('vin-report-no-membership')

    def vehicle(self, stock, vin, *, dealer=None, status='available'):
        return Vehicle.objects.create(dealership=dealer or self.dealer, stock_number=stock,
                                      vin=vin, year=2020, make='Synthetic', model='Example', status=status)

    def test_grouping_normalization_sold_blank_and_dealership_isolation(self):
        first = self.vehicle('LOCAL-A', ' \t example-vin\t ')
        second = self.vehicle('LOCAL-B', 'EXAMPLE-VIN', status='sold')
        self.vehicle('ONLY-LOCAL', 'FOREIGN-MATCH')
        self.vehicle('ONLY-FOREIGN', 'foreign-match', dealer=self.other)
        self.vehicle('FOREIGN-A', ' EXAMPLE-VIN ', dealer=self.other)
        self.vehicle('FOREIGN-B', 'example-vin', dealer=self.other)
        self.vehicle('BLANK-1', '')
        self.vehicle('BLANK-2', '   ')
        self.vehicle('BLANK-3', '\t')
        self.vehicle('BLANK-4', '\t')
        self.vehicle('BLANK-5', '\u00a0\t')
        self.client.force_login(self.users['viewer'])
        response = self.client.get(reverse('duplicate_vin_report'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([(v.pk, v.normalized_vin) for v in response.context['vehicles']],
                         [(first.pk, 'EXAMPLE-VIN'), (second.pk, 'EXAMPLE-VIN')])
        self.assertContains(response, reverse('vehicle_detail', args=[first.pk]))
        self.assertContains(response, reverse('vehicle_detail', args=[second.pk]))
        self.assertContains(response, 'Sold')
        self.assertContains(response, 'does not confirm a mistake or a reacquisition')
        self.assertNotContains(response, 'FOREIGN')
        self.assertNotContains(response, 'BLANK-')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(Vehicle.objects.filter(dealership=self.dealer).count(), 8)

    def test_pagination_caps_records_even_for_one_large_group(self):
        for index in range(28):
            self.vehicle(f'G-{index:02d}', 'same-vin')
        self.client.force_login(self.users['owner'])
        url = reverse('duplicate_vin_report')
        first = self.client.get(url)
        second = self.client.get(url, {'page': 2})
        self.assertEqual(first.context['page_obj'].paginator.count, 28)
        self.assertEqual(len(first.context['vehicles']), 25)
        self.assertEqual(len(second.context['vehicles']), 3)
        self.assertContains(first, 'Large groups may continue on the next page')
        self.assertContains(first, 'G-00')
        self.assertNotContains(first, 'G-27')
        self.assertContains(second, 'G-27')

    def test_access_gate_and_read_only_methods(self):
        url = reverse('duplicate_vin_report')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.no_membership)
        self.assertEqual(self.client.get(url).status_code, 403)
        for role in self.users:
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(self.client.head(url).status_code, 200)
            self.assertEqual(self.client.post(url).status_code, 405)
            self.assertContains(self.client.get(reverse('inventory')), 'Review duplicate VINs')
        with override_settings(DEBUG=False):
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertNotContains(self.client.get(reverse('inventory')), 'Review duplicate VINs')

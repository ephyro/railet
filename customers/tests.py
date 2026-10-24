# SPDX-License-Identifier: MPL-2.0
from django.test import TestCase

from core.models import Dealership
from .forms import CustomerChoiceField
from .models import Customer
from .queries import search_customers


class CustomerSearchTests(TestCase):
    def setUp(self):
        self.dealer = Dealership.objects.create(name="Synthetic search dealer")
        self.other = Dealership.objects.create(name="Other synthetic dealer")
        self.customer = Customer.objects.create(
            dealership=self.dealer, first_name="Riley", last_name="Demo",
            phone="+1 (202) 555-0123", email="riley@example.invalid",
        )
        Customer.objects.create(dealership=self.dealer, first_name="Riley", last_name="Different")
        Customer.objects.create(
            dealership=self.other, first_name="Riley", last_name="Demo",
            phone=self.customer.phone, email=self.customer.email,
        )

    def test_full_name_requires_all_words_and_keeps_dealership_scope(self):
        for query in ("Riley Demo", "Demo Riley", "RILEY DEMO", "riley@example.invalid"):
            with self.subTest(query=query):
                self.assertEqual(list(search_customers(self.dealer, query)), [self.customer])

    def test_formatted_phone_finds_normalized_number(self):
        for query in ("(202) 555-0123", "+1 202 555 0123", "5550123"):
            with self.subTest(query=query):
                self.assertEqual(list(search_customers(self.dealer, query)), [self.customer])

    def test_choices_distinguish_people_with_the_same_name(self):
        other_person = Customer.objects.create(
            dealership=self.dealer, first_name="Riley", last_name="Demo",
            email="another@example.invalid",
        )
        field = CustomerChoiceField(queryset=Customer.objects.filter(dealership=self.dealer))
        first_label = field.label_from_instance(self.customer)
        other_label = field.label_from_instance(other_person)
        self.assertIn(self.customer.phone, first_label)
        self.assertIn(other_person.email, other_label)
        self.assertNotEqual(first_label, other_label)

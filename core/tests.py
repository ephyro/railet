# SPDX-License-Identifier: MPL-2.0
import json
import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from customers.models import Customer
from deals.models import DraftDeal
from inventory.models import Vehicle
from .models import Dealership, Membership, SavedView


class SharedFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealership.objects.create(name="Synthetic filter dealer")
        cls.other = Dealership.objects.create(name="Other synthetic dealer")
        cls.user = get_user_model().objects.create_user(username="filter-owner")
        cls.colleague = get_user_model().objects.create_user(username="filter-colleague")
        cls.foreign_user = get_user_model().objects.create_user(username="filter-foreign")
        for user, dealer in ((cls.user, cls.dealer), (cls.colleague, cls.dealer), (cls.foreign_user, cls.other)):
            Membership.objects.create(user=user, dealership=dealer, role="owner")
        cls.available = Vehicle.objects.create(dealership=cls.dealer, stock_number="READY", year=2019, make="Honda", model="Civic", status="available", title_brand="unbranded", acquisition_cost="100.10")
        cls.rebuilt = Vehicle.objects.create(dealership=cls.dealer, stock_number="RECON", year=2010, make="Ford", model="Focus", status="recon", title_brand="rebuilt", acquisition_cost="150.20")
        cls.sold = Vehicle.objects.create(dealership=cls.dealer, stock_number="SOLD", year=2021, make="Honda", model="Accord", status="sold", title_received=True)
        cls.foreign = Vehicle.objects.create(dealership=cls.other, stock_number="PRIVATE", year=2019, make="Honda", model="Civic", status="available", title_brand="rebuilt")

    def setUp(self):
        self.client.force_login(self.user)

    def rules(self, fields, operators, values, uppers=None, **extra):
        return {"filter_field": fields, "filter_op": operators, "filter_value": values, "filter_to": uppers or [""] * len(fields), **extra}

    def test_all_any_rules_cannot_expand_dealership_scope(self):
        params = self.rules(["status", "brand"], ["eq", "eq"], ["available", "rebuilt"])
        all_page = self.client.get(reverse("inventory"), params)
        self.assertEqual(list(all_page.context["vehicles"]), [])
        any_page = self.client.get(reverse("inventory"), {**params, "match": "any"})
        self.assertEqual(set(any_page.context["vehicles"]), {self.available, self.rebuilt})
        self.assertNotContains(any_page, "Stock PRIVATE")

    def test_numeric_ranges_decimal_boundaries_dates_and_boolean_values(self):
        params = self.rules(["year", "cost"], ["between", "gte"], ["2011", "100.10"], ["2020", ""], sort="cost_low")
        page = self.client.get(reverse("inventory"), params)
        self.assertEqual(list(page.context["vehicles"]), [self.available])
        page = self.client.get(reverse("inventory"), self.rules(["title_received"], ["eq"], ["false"]))
        self.assertEqual(set(page.context["vehicles"]), {self.available, self.rebuilt})
        page = self.client.get(reverse("inventory"), self.rules(["updated"], ["gte"], ["2000-01-01"]))
        self.assertEqual(len(page.context["vehicles"]), 3)

    def test_text_comparisons_and_empty_values(self):
        page = self.client.get(reverse("inventory"), self.rules(["make"], ["not_contains"], ["Honda"]))
        self.assertEqual(list(page.context["vehicles"]), [self.rebuilt])
        page = self.client.get(reverse("inventory"), self.rules(["vin"], ["empty"], [""]))
        self.assertEqual(len(page.context["vehicles"]), 3)

    def test_invalid_fields_operators_values_and_sort_hide_results(self):
        bad_cases = [
            self.rules(["dealership_id"], ["eq"], [str(self.other.pk)]),
            self.rules(["make"], ["raw_sql"], ["Honda"]),
            self.rules(["year"], ["gte"], ["not a year"]),
            self.rules(["year"], ["between"], ["2025"], ["2010"]),
            self.rules(["cost"], ["eq"], ["NaN"]),
            self.rules(["status"], ["eq"], ["not-a-status"]),
            self.rules(["updated"], ["eq"], ["2026-99-99"]),
            self.rules(["title_received"], ["eq"], ["maybe"]),
            {"sort": "dealership__name"}, {"match": "xor"}, {"q": "bad\x00query"},
            self.rules(["make"], ["contains"], ["bad\x00value"]),
            self.rules(["make"] * 11, ["eq"] * 11, ["Honda"] * 11),
        ]
        for params in bad_cases:
            with self.subTest(params=params):
                page = self.client.get(reverse("inventory"), params)
                self.assertEqual(page.status_code, 200)
                self.assertEqual(list(page.context["vehicles"]), [])
                self.assertTrue(page.context["filter_state"].errors)

    def test_same_component_filters_customers_and_deals(self):
        customer = Customer.objects.create(dealership=self.dealer, first_name="Synthetic", last_name="Buyer", email="")
        foreign_customer = Customer.objects.create(dealership=self.other, first_name="Private", last_name="Buyer", email="")
        draft = DraftDeal.objects.create(dealership=self.dealer, buyer=customer, vehicle=self.available, sale_price="200.25")
        DraftDeal.objects.create(dealership=self.other, buyer=foreign_customer, vehicle=self.foreign, sale_price="200.25")
        people = self.client.get(reverse("customers"), self.rules(["email"], ["empty"], [""]))
        self.assertEqual(list(people.context["customers"]), [customer])
        drafts = self.client.get(reverse("deals"), self.rules(["price"], ["gte"], ["200.25"]))
        self.assertEqual(list(drafts.context["deals"]), [draft])
        self.assertContains(people, "data-filter-builder")
        self.assertContains(drafts, "data-filter-builder")

    def test_pagination_preserves_full_filter_definition(self):
        for number in range(26):
            Vehicle.objects.create(dealership=self.dealer, stock_number=f"PAGE-{number}", year=2018, make="Pagination", model="Example", status="recon")
        params = self.rules(["status", "make"], ["eq", "eq"], ["recon", "Pagination"], sort="name")
        first = self.client.get(reverse("inventory"), params)
        href = re.search(r'href="([^"]+)" aria-label="Next page"', first.content.decode()).group(1)
        following = parse_qs(urlsplit(unescape(href)).query)
        self.assertEqual(following["filter_field"], params["filter_field"])
        self.assertEqual(following["filter_value"], params["filter_value"])
        second = self.client.get(reverse("inventory"), following)
        self.assertEqual(len(first.context["vehicles"]), 25)
        self.assertEqual(len(second.context["vehicles"]), 1)
        self.assertEqual(second.context["page_obj"].paginator.count, 26)

    def test_rule_removal_links_preserve_other_criteria(self):
        extra = Vehicle.objects.create(dealership=self.dealer, stock_number="OTHER-2019", year=2019, make="Different", model="Car")
        params = self.rules(["make", "year"], ["eq", "between"], ["Honda", "2018"], ["", "2020"], sort="year_new")
        first = self.client.get(reverse("inventory"), params)
        self.assertEqual(list(first.context["vehicles"]), [self.available])
        remove = first.context["filter_state"].rows[0]["remove_query"]
        page = self.client.get(reverse("inventory") + "?" + remove)
        self.assertEqual(set(page.context["vehicles"]), {self.available, extra})
        self.assertEqual(page.context["filter_state"].sort, "year_new")
        self.assertEqual(page.context["filter_state"].rows[0]["field"], "year")

    def save_view(self, name="Rebuilt only", parameters=None):
        parameters = parameters if parameters is not None else {"filter_field": ["brand"], "filter_op": ["eq"], "filter_value": ["rebuilt"], "filter_to": [""]}
        return self.client.post(reverse("saved_view_create", args=["inventory"]), {"name": name, "parameters": json.dumps(parameters)})

    def test_saved_views_are_live_personal_and_dealership_scoped(self):
        response = self.save_view()
        self.assertEqual(response.status_code, 302)
        saved = SavedView.objects.get()
        self.assertEqual(saved.owner, self.user)
        self.assertEqual(saved.dealership, self.dealer)
        self.assertEqual(list(self.client.get(response["Location"]).context["vehicles"]), [self.rebuilt])
        extra = Vehicle.objects.create(dealership=self.dealer, stock_number="NEW-REBUILT", year=2020, make="New", model="Arrival", title_brand="rebuilt")
        self.assertEqual(set(self.client.get(response["Location"]).context["vehicles"]), {self.rebuilt, extra})
        for user in (self.colleague, self.foreign_user):
            self.client.force_login(user)
            self.assertEqual(self.client.get(response["Location"]).status_code, 404)
            self.assertEqual(self.client.post(reverse("saved_view_delete", args=[saved.pk])).status_code, 404)
        self.assertTrue(SavedView.objects.filter(pk=saved.pk).exists())

    def test_saved_view_names_do_not_overwrite_and_invalid_settings_are_preserved(self):
        self.save_view()
        duplicate = self.save_view(parameters={"status": ["sold"]})
        self.assertEqual(duplicate.status_code, 200)
        self.assertContains(duplicate, "already have a view")
        self.assertEqual(SavedView.objects.get().parameters["filter_value"], ["rebuilt"])
        for parameters in ("not-json", json.dumps({"dealership_id": [str(self.other.pk)]}), json.dumps({"q": "wrong-shape"})):
            page = self.client.post(reverse("saved_view_create", args=["inventory"]), {"name": "Keep my name", "parameters": parameters})
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, "Keep my name")
        self.assertEqual(SavedView.objects.count(), 1)

    def test_invalid_saved_settings_fail_closed_and_bad_ids_do_not_crash(self):
        saved = SavedView.objects.create(dealership=self.dealer, owner=self.user, resource="inventory", name="Old definition", parameters={"unknown": ["value"]})
        page = self.client.get(reverse("inventory"), {"view": saved.pk})
        self.assertEqual(list(page.context["vehicles"]), [])
        self.assertTrue(page.context["filter_state"].errors)
        for value in ("bad", "9" * 5000):
            self.assertEqual(self.client.get(reverse("inventory"), {"view": value}).status_code, 404)

    def test_viewer_can_save_preferences_without_writing_inventory(self):
        Membership.objects.filter(user=self.user).update(role="viewer")
        self.assertEqual(self.save_view().status_code, 302)
        self.assertEqual(Vehicle.objects.filter(dealership=self.dealer).count(), 3)
        saved = SavedView.objects.get()
        self.assertEqual(self.client.post(reverse("saved_view_delete", args=[saved.pk])).status_code, 302)
        self.assertFalse(SavedView.objects.exists())

    def test_saved_view_limit_and_resource_validation(self):
        SavedView.objects.bulk_create([SavedView(dealership=self.dealer, owner=self.user, resource="inventory", name=f"View {number}", parameters={}) for number in range(50)])
        self.assertContains(self.save_view(), "50 saved views")
        self.assertEqual(SavedView.objects.count(), 50)
        self.assertEqual(self.client.get(reverse("saved_view_create", args=["unknown"])).status_code, 404)

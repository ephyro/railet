# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4
from html import unescape
from urllib.parse import parse_qs, urlsplit
import re
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from core.models import Dealership, Membership
from customers.models import Customer, CustomerEvent
from inventory.models import Vehicle
from .models import DraftDeal, DealEvent, MONEY_FIELDS
from customers.services import save_customer

class DraftWorkflowTests(TestCase):
    def setUp(self):
        self.dealer = Dealership.objects.create(name="Synthetic A")
        self.other = Dealership.objects.create(name="Synthetic B")
        self.user = get_user_model().objects.create_user(username="staff", password="test-only-password")
        self.member = Membership.objects.create(user=self.user, dealership=self.dealer, role="staff")
        self.vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number="A", year=2020, make="Test", model="Car")
        self.buyer = Customer.objects.create(dealership=self.dealer, first_name="Test", last_name="Buyer", email="test@example.invalid")
        self.foreign = Customer.objects.create(dealership=self.other, first_name="Private", last_name="Person")
        self.client.force_login(self.user)
        self.data = {name: "0.00" for name in MONEY_FIELDS}
        self.data.update(vehicle=self.vehicle.pk, buyer=self.buyer.pk, customer_mode="existing", sale_price="10000.10", tax="600.00", down_payment="1000.00", submission_key=str(uuid4()))
    def test_existing_customer_reused_and_decimal_balance(self):
        response = self.client.post(reverse("deal_create"), self.data)
        self.assertEqual(response.status_code, 302)
        deal = DraftDeal.objects.get()
        self.assertEqual(deal.buyer_id, self.buyer.pk)
        self.assertEqual(Customer.objects.count(), 2)
        self.assertEqual(deal.draft_balance, Decimal("9600.10"))
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, "acquired")
        self.assertEqual(DealEvent.objects.count(), 1)
    def test_inline_customer_saved_once_with_deal(self):
        response = self.client.post(reverse("deal_create"), {**self.data, "customer_mode": "new", "buyer": "", "new-first_name": "New", "new-last_name": "Buyer"})
        self.assertEqual(response.status_code, 302)
        deal = DraftDeal.objects.get()
        self.assertEqual(deal.buyer.first_name, "New")
        self.assertEqual(CustomerEvent.objects.filter(customer=deal.buyer).count(), 1)
    def test_invalid_deal_does_not_create_inline_customer(self):
        response = self.client.post(reverse("deal_create"), {**self.data, "sale_price": "-1", "customer_mode": "new", "new-first_name": "New", "new-last_name": "Buyer"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Customer.objects.filter(first_name="New").exists())
        self.assertFalse(DraftDeal.objects.exists())
    def test_audit_failure_rolls_back_customer_and_deal(self):
        with patch("deals.services.DealEvent.objects.create", side_effect=RuntimeError("unavailable")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("deal_create"), {**self.data, "customer_mode": "new", "new-first_name": "New", "new-last_name": "Buyer"})
        self.assertFalse(Customer.objects.filter(first_name="New").exists())
        self.assertFalse(DraftDeal.objects.exists())
    def test_foreign_customer_and_vehicle_rejected(self):
        response = self.client.post(reverse("deal_create"), {**self.data, "buyer": self.foreign.pk})
        self.assertEqual(response.status_code, 200)
        foreign_car = Vehicle.objects.create(dealership=self.other, stock_number="B", year=2020, make="Other", model="Car")
        response = self.client.post(reverse("deal_create"), {**self.data, "vehicle": foreign_car.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DraftDeal.objects.exists())
    def test_same_buyer_and_co_buyer_rejected(self):
        self.assertEqual(self.client.post(reverse("deal_create"), {**self.data, "co_buyer": self.buyer.pk}).status_code, 200)
        self.assertFalse(DraftDeal.objects.exists())
    def test_viewer_cannot_create_customer_or_deal(self):
        self.member.role="viewer"; self.member.save()
        for route in ("customer_create", "deal_create"):
            self.assertEqual(self.client.post(reverse(route), self.data).status_code, 403)
    def test_foreign_records_not_readable(self):
        self.assertEqual(self.client.get(reverse("customer_detail", args=[self.foreign.pk])).status_code, 404)
        deal = DraftDeal.objects.create(dealership=self.other, vehicle=self.vehicle, buyer=self.foreign)
        self.assertEqual(self.client.get(reverse("deal_detail", args=[deal.pk])).status_code, 404)
    def test_stale_draft_edit_rejected(self):
        self.client.post(reverse("deal_create"), self.data)
        deal=DraftDeal.objects.get()
        self.assertEqual(self.client.post(reverse("deal_edit", args=[deal.pk]), {**self.data, "revision": 1, "sale_price": "11000.00"}).status_code, 302)
        self.assertEqual(self.client.post(reverse("deal_edit", args=[deal.pk]), {**self.data, "revision": 1, "sale_price": "12000.00"}).status_code, 409)
        deal.refresh_from_db();self.assertEqual(deal.sale_price,Decimal("11000.00"))
    def test_pages_render(self):
        for route in ("customers", "customer_create", "deals", "deal_create"):
            self.assertEqual(self.client.get(reverse(route)).status_code,200)
    def test_duplicate_customer_warning_is_dealer_scoped(self):
        data={"first_name":"Different","last_name":"Name","email":"TEST@example.invalid"}
        response=self.client.post(reverse("customer_create"),data)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,"matching details")
        self.assertEqual(self.client.post(reverse("customer_create"), {**data,"confirm_duplicate":"on"}).status_code,302)
    def test_customer_update_preserves_reference(self):
        deal=DraftDeal.objects.create(dealership=self.dealer, vehicle=self.vehicle, buyer=self.buyer)
        response=self.client.post(reverse("customer_edit",args=[self.buyer.pk]),{"first_name":"Updated","last_name":"Buyer","phone":"5550100","email":"test@example.invalid","revision":1})
        self.assertEqual(response.status_code,302)
        deal.refresh_from_db();self.assertEqual(deal.buyer.first_name,"Updated")
        self.assertEqual(deal.buyer_id,self.buyer.pk)
    def test_model_validation_rejects_cross_dealer_reference(self):
        deal=DraftDeal(dealership=self.dealer,vehicle=self.vehicle,buyer=self.foreign)
        with self.assertRaises(ValidationError):deal.full_clean()
    def test_co_buyer_profile_shows_shared_deal(self):
        co_buyer = Customer.objects.create(dealership=self.dealer, first_name="Co", last_name="Buyer")
        self.client.post(reverse("deal_create"), {**self.data, "co_buyer": co_buyer.pk})
        response = self.client.get(reverse("customer_detail", args=[co_buyer.pk]))
        self.assertEqual(list(response.context["drafts"]), [DraftDeal.objects.get()])
    def test_stale_customer_edit_rejected(self):
        self.buyer.revision = 2
        self.buyer.save()
        response = self.client.post(reverse("customer_edit", args=[self.buyer.pk]), {"first_name": "Changed", "last_name": "Buyer", "revision": 1})
        self.assertEqual(response.status_code, 409)
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.first_name, "Test")
    def test_phone_duplicates_normalized_without_cross_dealer_leak(self):
        self.buyer.phone = "+1 (555) 123-4567"
        self.buyer.save()
        response = self.client.post(reverse("customer_create"), {"first_name": "Different", "last_name": "Person", "phone": "555-123-4567"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["form"].matches), [self.buyer])

    def test_search_finds_co_buyer_contact_vehicle_and_draft_number(self):
        self.vehicle.stock_number = "SYN-042"
        self.vehicle.vin = "SYNTHETICVIN0042"
        self.vehicle.save()
        co_buyer = Customer.objects.create(dealership=self.dealer, first_name="Co", last_name="Signer", phone="+1 (202) 555-0123")
        draft = DraftDeal.objects.create(dealership=self.dealer, vehicle=self.vehicle, buyer=self.buyer, co_buyer=co_buyer)
        other_car = Vehicle.objects.create(dealership=self.other, stock_number="SYN-042", year=2020, make="Test", model="Car")
        self.foreign.first_name = "Co"
        self.foreign.last_name = "Signer"
        self.foreign.phone = co_buyer.phone
        self.foreign.save()
        DraftDeal.objects.create(dealership=self.other, vehicle=other_car, buyer=self.foreign)
        for query in ("Co Signer", "(202) 555-0123", "Test Buyer", "SYN-042", "SYNTHETICVIN0042", "2020 Test Car", f"#{draft.pk}"):
            with self.subTest(query=query):
                response = self.client.get(reverse("deals"), {"q": query})
                self.assertEqual(list(response.context["deals"]), [draft])

    def test_explicit_draft_number_is_exact_and_bad_number_is_harmless(self):
        draft = DraftDeal.objects.create(dealership=self.dealer, vehicle=self.vehicle, buyer=self.buyer)
        self.vehicle.stock_number = f"#{draft.pk}"
        self.vehicle.save()
        DraftDeal.objects.create(dealership=self.dealer, vehicle=self.vehicle, buyer=self.buyer)
        response = self.client.get(reverse("deals"), {"q": f"#{draft.pk}"})
        self.assertEqual(list(response.context["deals"]), [draft])
        for query in ("#bad", "#9999999999999999999999999999"):
            response = self.client.get(reverse("deals"), {"q": query})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(list(response.context["deals"]), [])

    def test_all_matching_drafts_and_customers_remain_accessible_on_later_pages(self):
        draft_ids, customer_ids = set(), set()
        for number in range(26):
            customer = Customer.objects.create(dealership=self.dealer, first_name="Search", last_name=f"Person {number:02}")
            customer_ids.add(customer.pk)
            draft_ids.add(DraftDeal.objects.create(dealership=self.dealer, vehicle=self.vehicle, buyer=customer).pk)
        for route, key, expected in (("deals", "deals", draft_ids), ("customers", "customers", customer_ids)):
            first = self.client.get(reverse(route), {"q": "Search Person"})
            second = self.client.get(reverse(route), {"q": "Search Person", "page": 2})
            first_ids = {item.pk for item in first.context[key]}
            second_ids = {item.pk for item in second.context[key]}
            self.assertEqual(len(first_ids), 25)
            self.assertEqual(len(second_ids), 1)
            self.assertFalse(first_ids & second_ids)
            self.assertEqual(first_ids | second_ids, expected)
            next_link = re.search(r'href="([^"]+)" aria-label="Next page"', first.content.decode()).group(1)
            next_params = parse_qs(urlsplit(unescape(next_link)).query)
            self.assertEqual(next_params["q"], ["Search Person"])
            self.assertEqual(next_params["page"], ["2"])

    def test_prefill_uses_scoped_choices_and_handles_invalid_ids(self):
        response = self.client.get(reverse("deal_create"), {"buyer": self.buyer.pk, "vehicle": self.vehicle.pk})
        self.assertEqual(response.context["form"].initial["buyer"], self.buyer.pk)
        self.assertEqual(response.context["form"].initial["vehicle"], self.vehicle.pk)
        other_car = Vehicle.objects.create(dealership=self.other, stock_number="FOREIGN", year=2020, make="Private", model="Car")
        for buyer, vehicle in ((self.foreign.pk, other_car.pk), ("bad", "bad"), ("9" * 5000, "9" * 5000)):
            response = self.client.get(reverse("deal_create"), {"buyer": buyer, "vehicle": vehicle})
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.context["form"].initial.get("buyer"))
            self.assertIsNone(response.context["form"].initial.get("vehicle"))
        self.vehicle.status = Vehicle.Status.SOLD
        self.vehicle.save()
        response = self.client.get(reverse("deal_create"), {"vehicle": self.vehicle.pk})
        self.assertIsNone(response.context["form"].initial.get("vehicle"))

    def test_empty_dealership_starts_with_inline_customer_entry(self):
        self.buyer.delete()
        response = self.client.get(reverse("deal_create"))
        self.assertEqual(response.context["mode"], "new")
        self.assertEqual(response.context["form"]["customer_mode"].value(), "new")

    def test_invalid_amount_stays_visible_and_preserves_input(self):
        response = self.client.post(reverse("deal_create"), {**self.data, "sale_price": "ten dollars"})
        self.assertContains(response, '<legend>Price and payments</legend>')
        self.assertEqual(response.context["form"]["sale_price"].value(), "ten dollars")
        self.assertFalse(DraftDeal.objects.exists())

    def test_repeated_creation_reopens_saved_draft_without_changing_it(self):
        first = self.client.post(reverse("deal_create"), self.data)
        repeated = self.client.post(reverse("deal_create"), {**self.data, "sale_price": "99999.00"})
        self.assertEqual(first.status_code, 302)
        self.assertEqual(repeated.status_code, 302)
        self.assertEqual(first["Location"], repeated["Location"])
        draft = DraftDeal.objects.get()
        self.assertEqual(draft.sale_price, Decimal("10000.10"))
        self.assertEqual(draft.revision, 1)
        self.assertEqual(DealEvent.objects.count(), 1)

    def test_repeated_inline_creation_does_not_duplicate_customer_or_audit(self):
        data = {**self.data, "customer_mode": "new", "buyer": "", "new-first_name": "Repeat", "new-last_name": "Buyer"}
        first = self.client.post(reverse("deal_create"), data)
        repeated = self.client.post(reverse("deal_create"), data)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(repeated["Location"], first["Location"])
        self.assertEqual(Customer.objects.filter(first_name="Repeat").count(), 1)
        self.assertEqual(DraftDeal.objects.count(), 1)
        self.assertEqual(CustomerEvent.objects.count(), 1)
        self.assertEqual(DealEvent.objects.count(), 1)

    def test_creation_key_is_scoped_to_dealership(self):
        other_car = Vehicle.objects.create(dealership=self.other, stock_number="OTHER", year=2020, make="Other", model="Car")
        foreign_draft = DraftDeal.objects.create(dealership=self.other, vehicle=other_car, buyer=self.foreign, creation_key=self.data["submission_key"])
        response = self.client.post(reverse("deal_create"), self.data)
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response["Location"], reverse("deal_detail", args=[foreign_draft.pk]))
        self.assertEqual(DraftDeal.objects.filter(dealership=self.dealer).count(), 1)

    def test_missing_creation_key_does_not_create_records(self):
        data = {**self.data, "customer_mode": "new", "buyer": "", "new-first_name": "Missing", "new-last_name": "Key"}
        data.pop("submission_key")
        response = self.client.post(reverse("deal_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("submission_key", response.context["form"].errors)
        self.assertFalse(Customer.objects.filter(first_name="Missing").exists())
        self.assertFalse(DraftDeal.objects.exists())

    def worksheet_data(self, **changes):
        return {**{name: self.data[name] for name in MONEY_FIELDS}, "notes": "", "revision": "1", **changes}

    def test_worksheet_saves_reference_amounts_without_changing_parties(self):
        self.client.post(reverse("deal_create"), self.data)
        deal = DraftDeal.objects.get()
        other_car = Vehicle.objects.create(dealership=self.other, stock_number="PRIVATE", year=2020, make="Other", model="Car")
        response = self.client.post(reverse("deal_detail", args=[deal.pk]), self.worksheet_data(
            sale_price="20000.00", tax="1300.00", title_registration="400.00", dealer_fee="300.00",
            trade_allowance="5000.00", trade_payoff="6500.00", down_payment="3000.00", notes="Worksheet reference case",
            buyer=self.foreign.pk, vehicle=other_car.pk,
        ))
        self.assertEqual(response.status_code, 302)
        deal.refresh_from_db()
        self.assertEqual(deal.draft_balance, Decimal("20500.00"))
        self.assertEqual(deal.buyer_id, self.buyer.pk)
        self.assertEqual(deal.vehicle_id, self.vehicle.pk)
        self.assertEqual(deal.revision, 2)
        self.assertEqual(DealEvent.objects.count(), 2)
        page = self.client.get(reverse("deal_detail", args=[deal.pk]))
        self.assertContains(page, "$20,500.00")
        self.assertEqual(page.context["totals"]["fees"], Decimal("2000.00"))

    def test_worksheet_viewer_can_read_but_cannot_save(self):
        self.client.post(reverse("deal_create"), self.data)
        deal = DraftDeal.objects.get()
        self.member.role = "viewer"
        self.member.save()
        page = self.client.get(reverse("deal_detail", args=[deal.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context["form"].fields["sale_price"].disabled)
        self.assertNotContains(page, "Save deal</button>")
        self.assertEqual(self.client.post(reverse("deal_detail", args=[deal.pk]), self.worksheet_data(sale_price="12345.00")).status_code, 403)
        deal.refresh_from_db()
        self.assertEqual(deal.sale_price, Decimal("10000.10"))

    def test_foreign_worksheet_is_not_readable_or_writable(self):
        other_car = Vehicle.objects.create(dealership=self.other, stock_number="FOREIGN-DESK", year=2020, make="Other", model="Car")
        deal = DraftDeal.objects.create(dealership=self.other, buyer=self.foreign, vehicle=other_car)
        url = reverse("deal_detail", args=[deal.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.worksheet_data()).status_code, 404)

    def test_worksheet_and_party_editor_share_stale_edit_protection(self):
        self.client.post(reverse("deal_create"), self.data)
        deal = DraftDeal.objects.get()
        url = reverse("deal_detail", args=[deal.pk])
        self.assertEqual(self.client.post(url, self.worksheet_data(sale_price="11000.00")).status_code, 302)
        stale = self.client.post(url, self.worksheet_data(sale_price="12000.00"))
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.context["form"]["sale_price"].value(), "12000.00")
        self.assertContains(stale, "Open the latest saved deal in a new tab", status_code=409)
        party_edit = self.client.post(reverse("deal_edit", args=[deal.pk]), {**self.data, "revision": 1})
        self.assertEqual(party_edit.status_code, 409)
        deal.refresh_from_db()
        self.assertEqual(deal.sale_price, Decimal("11000.00"))
        self.assertEqual(DealEvent.objects.count(), 2)

    def test_invalid_worksheet_keeps_entries_and_does_not_save(self):
        self.client.post(reverse("deal_create"), self.data)
        deal = DraftDeal.objects.get()
        url = reverse("deal_detail", args=[deal.pk])
        bad = self.client.post(url, self.worksheet_data(tax="not a number", notes="Keep this work"))
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(bad.context["form"]["tax"].value(), "not a number")
        self.assertEqual(bad.context["form"]["notes"].value(), "Keep this work")
        self.assertTrue(bad.context["fees_open"])
        negative = self.client.post(url, self.worksheet_data(down_payment="99999.00"))
        self.assertEqual(negative.status_code, 200)
        self.assertContains(negative, "Draft balance is below zero")
        deal.refresh_from_db()
        self.assertEqual(deal.notes, "")
        self.assertEqual(deal.revision, 1)
        self.assertEqual(DealEvent.objects.count(), 1)

    def test_unchanged_worksheet_does_not_manufacture_a_saved_revision(self):
        self.client.post(reverse("deal_create"), self.data)
        deal = DraftDeal.objects.get()
        response = self.client.post(reverse("deal_detail", args=[deal.pk]), self.worksheet_data())
        self.assertEqual(response.status_code, 302)
        deal.refresh_from_db()
        self.assertEqual(deal.revision, 1)
        self.assertEqual(DealEvent.objects.count(), 1)

    def test_worksheet_audit_failure_rolls_back_amounts_and_revision(self):
        self.client.post(reverse("deal_create"), self.data)
        deal = DraftDeal.objects.get()
        with patch("deals.services.DealEvent.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("deal_detail", args=[deal.pk]), self.worksheet_data(sale_price="15000.00"))
        deal.refresh_from_db()
        self.assertEqual(deal.sale_price, Decimal("10000.10"))
        self.assertEqual(deal.revision, 1)
        self.assertEqual(DealEvent.objects.count(), 1)

    def test_worksheet_save_returns_to_selected_section_and_rejects_unknown_sections(self):
        self.client.post(reverse("deal_create"), self.data)
        deal = DraftDeal.objects.get()
        url = reverse("deal_detail", args=[deal.pk])
        notes = self.client.post(url, self.worksheet_data(notes="Team note", active_section="notes"))
        self.assertEqual(notes["Location"], url + "#deal-notes")
        unknown = self.client.post(url, self.worksheet_data(notes="Team note", revision=2, active_section="https://example.invalid/"))
        self.assertEqual(unknown["Location"], url + "#deal-structure")


@skipUnless(connection.vendor == "postgresql", "Concurrent save verification requires PostgreSQL")
class ConcurrentDraftCreationTests(TransactionTestCase):
    def test_simultaneous_retries_commit_one_draft_and_one_inline_customer(self):
        dealer = Dealership.objects.create(name="Synthetic concurrency dealer")
        user = get_user_model().objects.create_user(username="concurrent-staff", password="test-only-password")
        Membership.objects.create(user=user, dealership=dealer, role="staff")
        vehicle = Vehicle.objects.create(dealership=dealer, stock_number="CONCURRENT", year=2020, make="Test", model="Car")
        data = {name: "0.00" for name in MONEY_FIELDS}
        data.update(vehicle=vehicle.pk, customer_mode="new", buyer="", **{"new-first_name": "Concurrent", "new-last_name": "Buyer", "submission_key": str(uuid4())})
        both_ready = Barrier(2)

        def submit():
            close_old_connections()
            try:
                client = Client()
                client.force_login(user)
                # Synchronize before the request; draft creation now locks the dealer
                # before inline validation/save, so a barrier inside save would deadlock.
                both_ready.wait(timeout=20)
                response = client.post(reverse("deal_create"), data)
                return response.status_code, response.get("Location")
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(submit) for _ in range(2)]
            responses = [future.result(timeout=35) for future in futures]

        self.assertEqual([status for status, _ in responses], [302, 302])
        self.assertEqual(responses[0][1], responses[1][1])
        self.assertEqual(DraftDeal.objects.count(), 1)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(CustomerEvent.objects.count(), 1)
        self.assertEqual(DealEvent.objects.count(), 1)


class DraftCreationKeyMigrationTests(TransactionTestCase):
    def test_existing_drafts_get_distinct_keys_without_changing_amounts(self):
        previous = [("deals", "0001_initial"), ("inventory", "0003_vehiclephoto"), ("customers", "0001_initial")]
        current = [("deals", "0002_draft_creation_key"), ("inventory", "0003_vehiclephoto"), ("customers", "0001_initial")]
        executor = MigrationExecutor(connection)
        try:
            executor.migrate(previous)
            old_apps = executor.loader.project_state(previous).apps
            dealer = old_apps.get_model("core", "Dealership").objects.create(name="Synthetic migration dealer")
            customer = old_apps.get_model("customers", "Customer").objects.create(dealership=dealer, first_name="Migration", last_name="Buyer")
            vehicle = old_apps.get_model("inventory", "Vehicle").objects.create(dealership=dealer, stock_number="MIGRATION", year=2020, make="Test", model="Car")
            old_drafts = old_apps.get_model("deals", "DraftDeal")
            ids = [old_drafts.objects.create(dealership=dealer, buyer=customer, vehicle=vehicle, sale_price="1234.56").pk for _ in range(2)]
            actor_id = get_user_model().objects.create_user(username="migration-actor").pk
            event_id = old_apps.get_model("deals", "DealEvent").objects.create(deal_id=ids[0], actor_id=actor_id, snapshot={"legacy": "unchanged"}).pk
            executor = MigrationExecutor(connection)
            executor.migrate(current)
            migrated = executor.loader.project_state(current).apps.get_model("deals", "DraftDeal")
            rows = list(migrated.objects.filter(pk__in=ids).values_list("creation_key", "sale_price"))
            self.assertEqual(len(rows), 2)
            self.assertEqual(len({key for key, _ in rows}), 2)
            self.assertTrue(all(key and amount == Decimal("1234.56") for key, amount in rows))
            latest = [("deals", "0003_draftfinanceproposal_draftdeal_deal_type_and_more")]
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            latest_apps = executor.loader.project_state(latest).apps
            self.assertEqual(list(latest_apps.get_model("deals", "DraftDeal").objects.filter(pk__in=ids).values_list("deal_type", flat=True)), ["undecided", "undecided"])
            self.assertEqual(latest_apps.get_model("deals", "DraftFinanceProposal").objects.count(), 0)
            executor = MigrationExecutor(connection)
            leaves = executor.loader.graph.leaf_nodes()
            executor.migrate(leaves)
            apps = executor.loader.project_state(leaves).apps
            self.assertEqual(apps.get_model("deals", "DraftTradeIn").objects.count(), 0)
            migrated_vehicle = apps.get_model("inventory", "Vehicle").objects.get(pk=vehicle.pk)
            self.assertIsNone(migrated_vehicle.odometer_reading)
            self.assertEqual(migrated_vehicle.odometer_status, "unknown")
            self.assertEqual(apps.get_model("deals", "DealEvent").objects.get(pk=event_id).snapshot, {"legacy": "unchanged"})
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

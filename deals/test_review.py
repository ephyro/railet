# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from core.models import AuditEvent, Dealership, Membership
from customers.models import Customer
from inventory.models import Vehicle

from .models import DealEvent, DealType, DraftDeal, DraftFinanceProposal, DraftTradeIn


class DraftDealReviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.dealer = Dealership.objects.create(name="Synthetic review dealer")
        cls.other_dealer = Dealership.objects.create(name="Other synthetic dealer")
        cls.user = user_model.objects.create_user(username="review-owner", password="test-only")
        cls.viewer = user_model.objects.create_user(username="review-viewer", password="test-only")
        cls.foreign_user = user_model.objects.create_user(username="review-foreign", password="test-only")
        Membership.objects.create(user=cls.user, dealership=cls.dealer, role=Membership.Role.OWNER)
        Membership.objects.create(user=cls.viewer, dealership=cls.dealer, role=Membership.Role.VIEWER)
        Membership.objects.create(user=cls.foreign_user, dealership=cls.other_dealer, role=Membership.Role.OWNER)
        cls.vehicle = Vehicle.objects.create(
            dealership=cls.dealer,
            stock_number="SYN-REVIEW-01",
            year=2020,
            make="Synthetic",
            model="Sedan",
        )
        cls.buyer = Customer.objects.create(
            dealership=cls.dealer,
            first_name="Synthetic",
            last_name="Buyer",
            phone="555-0101",
            email="buyer@example.invalid",
        )
        cls.deal = DraftDeal.objects.create(
            dealership=cls.dealer,
            vehicle=cls.vehicle,
            buyer=cls.buyer,
        )
        cls.foreign_vehicle = Vehicle.objects.create(
            dealership=cls.other_dealer,
            stock_number="PRIVATE-FOREIGN",
            year=2021,
            make="Private",
            model="Vehicle",
            vin="PRIVATE-FOREIGN-VIN",
        )
        cls.foreign_buyer = Customer.objects.create(
            dealership=cls.other_dealer,
            first_name="Private",
            last_name="Customer",
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("deal_review", args=[self.deal.pk])

    def test_cross_dealership_drafts_and_corrupt_related_records_return_404(self):
        foreign_deal = DraftDeal.objects.create(
            dealership=self.other_dealer,
            vehicle=self.foreign_vehicle,
            buyer=self.foreign_buyer,
        )
        response = self.client.get(reverse("deal_review", args=[foreign_deal.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "PRIVATE-FOREIGN-VIN", status_code=404)

        mismatched_deal = DraftDeal.objects.create(
            dealership=self.dealer,
            vehicle=self.foreign_vehicle,
            buyer=self.buyer,
        )
        self.assertEqual(
            self.client.get(reverse("deal_review", args=[mismatched_deal.pk])).status_code,
            404,
        )

    def test_unauthenticated_request_redirects_to_login(self):
        response = Client().get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_viewers_can_read_but_receive_no_edit_links(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Draft worksheet")
        self.assertNotContains(response, reverse("deal_edit", args=[self.deal.pk]))
        self.assertNotContains(response, reverse("vehicle_edit", args=[self.vehicle.pk]))
        self.assertNotContains(response, reverse("customer_edit", args=[self.buyer.pk]))
        self.assertEqual(self.client.head(self.url).status_code, 200)

    def test_post_is_denied_without_mutating_deal_related_records_or_money(self):
        before_deal = DraftDeal.objects.filter(pk=self.deal.pk).values().get()
        before_vehicle = Vehicle.objects.filter(pk=self.vehicle.pk).values().get()
        before_buyer = Customer.objects.filter(pk=self.buyer.pk).values().get()
        before_counts = (
            DraftTradeIn.objects.count(),
            DraftFinanceProposal.objects.count(),
            DealEvent.objects.count(),
            AuditEvent.objects.count(),
        )

        response = self.client.post(self.url, {"sale_price": "999999.99", "deal_type": "cash"})

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], "GET, HEAD")
        self.assertEqual(DraftDeal.objects.filter(pk=self.deal.pk).values().get(), before_deal)
        self.assertEqual(Vehicle.objects.filter(pk=self.vehicle.pk).values().get(), before_vehicle)
        self.assertEqual(Customer.objects.filter(pk=self.buyer.pk).values().get(), before_buyer)
        self.assertEqual(
            (
                DraftTradeIn.objects.count(),
                DraftFinanceProposal.objects.count(),
                DealEvent.objects.count(),
                AuditEvent.objects.count(),
            ),
            before_counts,
        )

    def test_get_and_head_are_read_only(self):
        before_deal = DraftDeal.objects.filter(pk=self.deal.pk).values().get()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.head(self.url).status_code, 200)
        self.assertEqual(DraftDeal.objects.filter(pk=self.deal.pk).values().get(), before_deal)
        self.assertEqual(DealEvent.objects.count(), 0)

    def test_authenticated_review_responses_are_private_and_not_stored(self):
        for response in (self.client.get(self.url), self.client.head(self.url)):
            with self.subTest(method=response.request["REQUEST_METHOD"]):
                self.assertEqual(response.status_code, 200)
                self.assertIn("private", response["Cache-Control"])
                self.assertIn("no-store", response["Cache-Control"])

    def test_title_received_fact_and_evidence_follow_up_reflect_saved_value(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-review-field="vehicle-title-received">No</dd>')
        self.assertContains(response, "Vehicle title is not marked as received.")
        self.assertContains(response, "Follow up on the title evidence for this vehicle.")

        self.vehicle.title_received = True
        self.vehicle.save()
        response = self.client.get(self.url)
        self.assertContains(response, 'data-review-field="vehicle-title-received">Yes</dd>')
        self.assertNotContains(response, "Vehicle title is not marked as received.")

    def test_unknown_values_stay_unknown_and_explicit_zero_stays_visible(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Not recorded")
        self.assertContains(response, "Not verified")
        self.assertNotContains(response, "No brand recorded")
        self.assertNotContains(response, "Actual mileage reported")

        self.vehicle.odometer_reading = 0
        self.vehicle.odometer_unit = "miles"
        self.vehicle.odometer_status = "actual"
        self.vehicle.title_brand = "unbranded"
        self.vehicle.save()
        response = self.client.get(self.url)
        self.assertContains(response, "0\n        · Miles")
        self.assertContains(response, "Actual mileage reported")
        self.assertContains(response, "No brand recorded")

        self.deal.deal_type = DealType.BHPH
        self.deal.save()
        proposal = DraftFinanceProposal.objects.create(deal=self.deal, kind=DealType.BHPH)
        response = self.client.get(self.url)
        self.assertContains(response, 'data-review-field="proposal-5">Not recorded</dd>')
        proposal.annual_contract_rate = Decimal("0.0000")
        proposal.save()
        response = self.client.get(self.url)
        self.assertContains(response, 'data-review-field="proposal-5">0.0000%</dd>')

    def test_undecided_deal_does_not_infer_cash_no_brand_or_actual_mileage(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Not chosen")
        self.assertNotContains(response, "Cash")
        self.assertNotContains(response, "No brand recorded")
        self.assertNotContains(response, "Actual mileage reported")

    def test_only_proposal_matching_selected_financing_type_is_shown(self):
        self.deal.deal_type = DealType.BHPH
        self.deal.save()
        DraftFinanceProposal.objects.create(
            deal=self.deal,
            kind=DealType.BHPH,
            creditor_name="Selected synthetic BHPH proposal",
            payment_count=24,
            annual_contract_rate=Decimal("0.0000"),
        )
        DraftFinanceProposal.objects.create(
            deal=self.deal,
            kind=DealType.OUTSIDE,
            creditor_name="Inactive synthetic outside proposal",
            payment_count=48,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_proposal"].kind, DealType.BHPH)
        self.assertContains(response, "Selected synthetic BHPH proposal")
        self.assertNotContains(response, "Inactive synthetic outside proposal")
        self.assertContains(response, "Annual contract rate entered (not APR)")

    def test_financing_links_and_reminders_target_proposal_section(self):
        self.deal.deal_type = DealType.BHPH
        self.deal.save()
        proposal_url = reverse("deal_detail", args=[self.deal.pk]) + "#deal-structure"
        response = self.client.get(self.url)

        self.assertContains(response, f'href="{proposal_url}">Edit proposal</a>')
        self.assertContains(response, f'href="{proposal_url}">Review deal</a>')
        self.assertContains(
            response,
            f'href="{reverse("deal_edit", args=[self.deal.pk])}#buyer">Add co-buyer</a>',
        )

        DraftFinanceProposal.objects.create(deal=self.deal, kind=DealType.BHPH)
        response = self.client.get(self.url)
        self.assertContains(response, f'href="{proposal_url}">Edit proposal</a>')
        self.assertContains(response, f'href="{proposal_url}">Review deal</a>')

    def test_trade_and_exact_negative_equity_worksheet_balance_are_shown(self):
        DraftDeal.objects.filter(pk=self.deal.pk).update(
            sale_price=Decimal("10000.10"),
            tax=Decimal("500.25"),
            title_registration=Decimal("100.00"),
            dealer_fee=Decimal("250.00"),
            trade_allowance=Decimal("1500.00"),
            trade_payoff=Decimal("2500.00"),
            down_payment=Decimal("2000.25"),
        )
        DraftTradeIn.objects.create(
            deal=self.deal,
            vin="SYNTHETIC-TRADE-001",
            year=2012,
            make="Synthetic",
            model="Trade",
            title_brand="rebuilt",
            odometer_reading=123456,
            odometer_unit="miles",
            odometer_status="not_actual",
            lienholder_name="Synthetic payoff recipient",
            payoff_good_through="2026-11-15",
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SYNTHETIC-TRADE-001")
        self.assertContains(response, "Synthetic payoff recipient")
        self.assertContains(response, "$1,500.00")
        self.assertContains(response, "$2,500.00")
        self.assertContains(response, "Trade payoff less allowance")
        self.assertContains(response, "$1,000.00")
        self.assertContains(response, "$9,850.10")

    def test_recorded_customer_and_vehicle_text_is_html_escaped(self):
        self.buyer.first_name = "<script>alert(1)</script>"
        self.buyer.save()
        self.vehicle.make = "<img src=x onerror=alert(1)>"
        self.vehicle.save()

        response = self.client.get(self.url)
        body = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", body)
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertNotIn("<img src=x onerror=alert(1)>", body)

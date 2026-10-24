# SPDX-License-Identifier: MPL-2.0
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from core.models import AuditEvent, Dealership, Membership
from customers.models import Customer
from deals.models import DraftDeal, DraftTradeIn

from .models import Vehicle
from .vin_matching import matching_vehicles


class DuplicateVinReviewTests(TestCase):
    def setUp(self):
        self.dealer = Dealership.objects.create(name="Synthetic VIN review dealer")
        self.other_dealer = Dealership.objects.create(name="Other synthetic dealer")
        self.user = get_user_model().objects.create_user(username="vin-review-owner", password="test-only")
        self.viewer = get_user_model().objects.create_user(username="vin-review-viewer", password="test-only")
        self.member = Membership.objects.create(user=self.user, dealership=self.dealer, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.viewer, dealership=self.dealer, role=Membership.Role.VIEWER)
        self.client.force_login(self.user)
        self.create_url = reverse("vehicle_create")
        self.base_data = {
            "stock_number": "NEW-STOCK",
            "vin": "",
            "year": "2021",
            "make": "Synthetic",
            "model": "Example",
            "status": "available",
            "title_brand": "unknown",
            "title_received": "",
            "odometer_reading": "",
            "odometer_unit": "unknown",
            "odometer_status": "unknown",
            "acquisition_cost": "0.00",
            "recon_cost": "0.00",
            "notes": "Synthetic test record",
        }

    def vehicle(self, *, stock, vin, status="available", dealership=None, model="Match vehicle"):
        return Vehicle.objects.create(
            dealership=dealership or self.dealer,
            stock_number=stock,
            vin=vin,
            year=2019,
            make="Synthetic",
            model=model,
            status=status,
        )

    def post_create(self, **changes):
        return self.client.post(self.create_url, {**self.base_data, **changes})

    def test_create_collision_shows_same_dealer_active_and_sold_records(self):
        active = self.vehicle(stock="ACTIVE-1", vin="SYNTHETIC-ACTIVE-VIN", status="available")
        sold = self.vehicle(stock="SOLD-1", vin=" synthetic-active-vin ", status="sold")

        response = self.post_create(vin="Synthetic-Active-Vin", dealership=self.other_dealer.pk)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review matching VIN records")
        self.assertContains(response, "Stock ACTIVE-1")
        self.assertContains(response, "Stock SOLD-1")
        self.assertContains(response, "Available")
        self.assertContains(response, "Sold")
        self.assertContains(response, reverse("vehicle_detail", args=[active.pk]))
        self.assertContains(response, reverse("vehicle_detail", args=[sold.pk]))
        self.assertContains(response, "reacquisition")
        self.assertEqual(Vehicle.objects.filter(dealership=self.dealer).count(), 2)
        self.assertFalse(AuditEvent.objects.exists())

    def test_vin_change_collision_is_blocked_before_any_update(self):
        current = self.vehicle(stock="CURRENT", vin="OLD-VIN", model="Current record")
        match = self.vehicle(stock="MATCH", vin="NEW-VIN", status="sold")
        response = self.client.post(
            reverse("vehicle_edit", args=[current.pk]),
            {
                **self.base_data,
                "stock_number": current.stock_number,
                "vin": " new-vin ",
                "notes": "Keep this pending edit",
                "revision": current.revision,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stock MATCH")
        self.assertContains(response, "Keep this pending edit")
        current.refresh_from_db()
        self.assertEqual(current.vin, "OLD-VIN")
        self.assertEqual(current.notes, "")
        self.assertEqual(current.revision, 1)
        self.assertFalse(AuditEvent.objects.filter(vehicle=current).exists())
        self.assertTrue(Vehicle.objects.filter(pk=match.pk).exists())

    def test_blank_vin_is_exempt_and_normalized_legacy_vin_matches(self):
        blank = self.post_create(vin="  ", stock_number="BLANK-VIN")
        self.assertEqual(blank.status_code, 302)
        self.assertEqual(Vehicle.objects.get(stock_number="BLANK-VIN").vin, "")

        legacy = self.vehicle(stock="LEGACY", vin="  old-vin-42  ")
        match = self.post_create(vin=" OLD-VIN-42 ", stock_number="NEW-LEGACY")
        self.assertEqual(match.status_code, 200)
        self.assertContains(match, "Stock LEGACY")
        self.assertEqual(list(matching_vehicles(dealership=self.dealer, vin="old-vin-42").values_list("pk", flat=True)), [legacy.pk])

    def test_cross_dealership_record_does_not_block_or_leak(self):
        foreign = self.vehicle(
            stock="PRIVATE-STOCK",
            vin="CROSS-DEALER-VIN",
            dealership=self.other_dealer,
            model="Private vehicle description",
        )

        response = self.post_create(vin="cross-dealer-vin", stock_number="LOCAL-STOCK")

        self.assertEqual(response.status_code, 302)
        created = Vehicle.objects.get(stock_number="LOCAL-STOCK")
        self.assertEqual(created.dealership, self.dealer)
        self.assertEqual(created.vin, "CROSS-DEALER-VIN")
        self.assertNotContains(response, "PRIVATE-STOCK", status_code=302)
        self.assertTrue(Vehicle.objects.filter(pk=foreign.pk).exists())
        self.assertNotIn("duplicate_vin_review", AuditEvent.objects.get(vehicle=created).changes)

    def test_unchanged_normalized_duplicate_vin_allows_unrelated_edit(self):
        current = self.vehicle(stock="DUP-A", vin="same-vin")
        self.vehicle(stock="DUP-B", vin=" SAME-VIN ", status="sold")

        response = self.client.post(
            reverse("vehicle_edit", args=[current.pk]),
            {
                **self.base_data,
                "stock_number": current.stock_number,
                "vin": " Same-Vin ",
                "notes": "Updated notes only",
                "revision": current.revision,
            },
        )

        self.assertEqual(response.status_code, 302)
        current.refresh_from_db()
        self.assertEqual(current.notes, "Updated notes only")
        self.assertEqual(current.revision, 2)
        event = AuditEvent.objects.get(vehicle=current)
        self.assertNotIn("duplicate_vin_review", event.changes)

    def test_missing_acknowledgement_or_reason_preserves_entries_without_writes(self):
        self.vehicle(stock="EXISTING", vin="REVIEW-ME")
        missing_both = self.post_create(vin="review-me", notes="Preserve my entered notes")

        self.assertEqual(missing_both.status_code, 200)
        self.assertContains(missing_both, "Preserve my entered notes")
        self.assertContains(missing_both, "Review the matching records and check this box")
        self.assertContains(missing_both, "Enter a reason for keeping this as a separate vehicle record")
        self.assertContains(missing_both, "id_duplicate_review_acknowledged")
        self.assertContains(missing_both, "id_duplicate_review_reason")
        self.assertEqual(Vehicle.objects.filter(dealership=self.dealer).count(), 1)
        self.assertFalse(AuditEvent.objects.exists())

        missing_reason = self.post_create(
            vin="review-me",
            duplicate_review_acknowledged="on",
            notes="Preserve this too",
        )
        self.assertEqual(missing_reason.status_code, 200)
        self.assertContains(missing_reason, "Preserve this too")
        self.assertContains(missing_reason, "Enter a reason for keeping this as a separate vehicle record")
        self.assertEqual(Vehicle.objects.filter(dealership=self.dealer).count(), 1)
        self.assertFalse(AuditEvent.objects.exists())

    def test_acknowledged_review_audits_exact_matched_ids_actor_and_reason(self):
        match_a = self.vehicle(stock="MATCH-A", vin="DUPLICATE-REVIEW")
        match_b = self.vehicle(stock="MATCH-B", vin=" duplicate-review ", status="sold")
        reason = "Reacquired vehicle after legacy stock correction"

        response = self.post_create(
            vin="Duplicate-Review",
            stock_number="REACQUIRED",
            duplicate_review_acknowledged="on",
            duplicate_review_reason=f"  {reason}  ",
            duplicate_ids="999999",
            dealership=self.other_dealer.pk,
        )

        self.assertEqual(response.status_code, 302)
        saved = Vehicle.objects.get(stock_number="REACQUIRED")
        event = AuditEvent.objects.get(vehicle=saved)
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.dealership, self.dealer)
        self.assertEqual(
            event.changes["duplicate_vin_review"],
            {
                "before": None,
                "after": {
                    "matched_vehicle_ids": [match_a.pk, match_b.pk],
                    "reason": reason,
                },
            },
        )

    def test_forged_acknowledgement_without_conflict_has_no_review_metadata(self):
        response = self.post_create(
            vin="UNIQUE-VIN",
            duplicate_review_acknowledged="on",
            duplicate_review_reason="Forged review field",
            duplicate_ids="123,456",
            skip_duplicate_review="on",
        )

        self.assertEqual(response.status_code, 302)
        saved = Vehicle.objects.get(stock_number="NEW-STOCK")
        self.assertNotIn("duplicate_vin_review", AuditEvent.objects.get(vehicle=saved).changes)

    def test_stale_revision_keeps_submitted_work_without_override(self):
        current = self.vehicle(stock="STALE", vin="STALE-OLD")
        self.vehicle(stock="CURRENT-MATCH", vin="STALE-NEW", status="sold")
        current.revision = 2
        current.save(update_fields=["revision"])
        event_count = AuditEvent.objects.count()

        response = self.client.post(
            reverse("vehicle_edit", args=[current.pk]),
            {
                **self.base_data,
                "stock_number": current.stock_number,
                "vin": "STALE-NEW",
                "notes": "Preserve stale entered work",
                "revision": "1",
                "duplicate_review_acknowledged": "on",
                "duplicate_review_reason": "Would be a reacquisition",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "Preserve stale entered work", status_code=409)
        self.assertContains(response, "Stock CURRENT-MATCH", status_code=409)
        current.refresh_from_db()
        self.assertEqual((current.vin, current.notes, current.revision), ("STALE-OLD", "", 2))
        self.assertEqual(AuditEvent.objects.count(), event_count)

    def test_viewer_denial_and_csrf_protection_remain(self):
        self.client.force_login(self.viewer)
        self.vehicle(stock="CSRF-MATCH", vin="CSRF-VIN")
        self.assertEqual(self.client.post(self.create_url, {**self.base_data, "vin": "CSRF-VIN"}).status_code, 403)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.create_url, {**self.base_data, "vin": "CSRF-VIN"}).status_code, 403)

    def test_audit_failure_rolls_back_acknowledged_duplicate_creation(self):
        self.vehicle(stock="AUDIT-MATCH", vin="AUDIT-VIN")
        with patch("inventory.views.AuditEvent.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.post_create(
                    vin="AUDIT-VIN",
                    stock_number="AUDIT-NEW",
                    duplicate_review_acknowledged="on",
                    duplicate_review_reason="Synthetic reacquisition",
                )

        self.assertFalse(Vehicle.objects.filter(stock_number="AUDIT-NEW").exists())
        self.assertEqual(Vehicle.objects.filter(dealership=self.dealer).count(), 1)


@skipUnless(connection.vendor == "postgresql", "Dealership row-lock concurrency requires PostgreSQL")
@override_settings(TRADE_INTAKE_DEMO_ENABLED=True)
class ConcurrentOrdinaryVinCreationTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.dealer = Dealership.objects.create(name="Synthetic concurrent VIN dealer")
        self.user = get_user_model().objects.create_user(username="vin-concurrent-owner", password="test-only")
        Membership.objects.create(user=self.user, dealership=self.dealer, role=Membership.Role.OWNER)
        self.vehicle_data = {
            "year": "2021",
            "make": "Synthetic",
            "model": "Concurrent",
            "status": "available",
            "title_brand": "unknown",
            "acquisition_cost": "0.00",
            "recon_cost": "0.00",
        }

    def _parallel_post(self, requests):
        barrier = Barrier(len(requests))
        user_id = self.user.pk

        def send(url, data):
            close_old_connections()
            try:
                client = Client()
                client.force_login(get_user_model().objects.get(pk=user_id))
                barrier.wait(timeout=10)
                response = client.post(url, data)
                return response.status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            futures = [pool.submit(send, url, data) for url, data in requests]
            return [future.result(timeout=30) for future in futures]

    def _ordinary_data(self, stock, vin):
        return {
            **self.vehicle_data,
            "stock_number": stock,
            "vin": vin,
            "title_received": "",
            "odometer_reading": "",
            "odometer_unit": "unknown",
            "odometer_status": "unknown",
        }

    def test_simultaneous_ordinary_creates_same_vin_allow_only_one_vehicle(self):
        requests = [
            (reverse("vehicle_create"), self._ordinary_data("RACE-A", "SAME-RACE-VIN")),
            (reverse("vehicle_create"), self._ordinary_data("RACE-B", " same-race-vin ")),
        ]

        statuses = self._parallel_post(requests)

        self.assertEqual(sorted(statuses), [200, 302])
        self.assertEqual(matching_vehicles(dealership=self.dealer, vin="SAME-RACE-VIN").count(), 1)

    def test_simultaneous_ordinary_create_and_trade_intake_allow_only_one_vehicle(self):
        sale_vehicle = Vehicle.objects.create(
            dealership=self.dealer,
            stock_number="SALE-STOCK",
            vin="SALE-VEHICLE-VIN",
            year=2022,
            make="Synthetic",
            model="Sale vehicle",
        )
        buyer = Customer.objects.create(dealership=self.dealer, first_name="Synthetic", last_name="Buyer")
        deal = DraftDeal.objects.create(dealership=self.dealer, vehicle=sale_vehicle, buyer=buyer)
        trade = DraftTradeIn.objects.create(
            deal=deal,
            vin="RACE-TRADE-VIN",
            year=2015,
            make="Synthetic",
            model="Trade vehicle",
        )
        trade_url = reverse("trade_intake", args=[deal.pk, trade.pk])
        ordinary_url = reverse("vehicle_create")
        requests = [
            (
                ordinary_url,
                self._ordinary_data("ORDINARY-RACE", "race-trade-vin"),
            ),
            (
                trade_url,
                {
                    "revision": "1",
                    "stock_number": "TRADE-RACE",
                    "acquisition_cost": "100.00",
                    "title_received": "",
                    "confirm": "on",
                },
            ),
        ]

        ordinary_status, trade_status = self._parallel_post(requests)

        self.assertEqual(sorted((ordinary_status, trade_status)), [200, 302])
        self.assertEqual(matching_vehicles(dealership=self.dealer, vin="RACE-TRADE-VIN").count(), 1)
        deal.refresh_from_db()
        trade.refresh_from_db()
        if trade_status == 302:
            self.assertEqual(deal.revision, 2)
            self.assertTrue(trade.inventory_vehicle_id)
            self.assertFalse(Vehicle.objects.filter(stock_number="ORDINARY-RACE").exists())
        else:
            self.assertEqual(ordinary_status, 302)
            self.assertEqual(deal.revision, 1)
            self.assertIsNone(trade.inventory_vehicle_id)
            self.assertTrue(Vehicle.objects.filter(stock_number="ORDINARY-RACE").exists())

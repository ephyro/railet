# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from core.models import Dealership, Membership, AuditEvent
from .models import Vehicle

class InventorySecurityTests(TestCase):
    def setUp(self):
        self.dealer = Dealership.objects.create(name="Synthetic A")
        self.other = Dealership.objects.create(name="Synthetic B")
        self.user = get_user_model().objects.create_user(username="owner", password="test-only-password")
        self.member = Membership.objects.create(user=self.user, dealership=self.dealer, role="owner")
        self.vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number="A-1", year=2020, make="Test", model="Local")
        self.foreign = Vehicle.objects.create(dealership=self.other, stock_number="B-1", year=2020, make="Private", model="Foreign")
        self.data = dict(stock_number="NEW", year=2021, make="Test", model="New", status="recon", title_brand="rebuilt", acquisition_cost="100.10", recon_cost="0.20", notes="Synthetic")
        self.client.force_login(self.user)
    def test_anonymous_redirects(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("inventory")).status_code, 302)
    def test_inline_vehicle_rechecks_actor_membership(self):
        from .inline import InlineVehicleForm, create_inline_vehicle
        for revoked in ('inactive', 'viewer', 'foreign', 'removed'):
            with self.subTest(revoked=revoked):
                form = InlineVehicleForm(self.data, dealership=self.dealer)
                self.assertTrue(form.is_valid(), form.errors)
                if revoked == 'inactive':
                    get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
                elif revoked == 'viewer':
                    Membership.objects.filter(pk=self.member.pk).update(role='viewer')
                elif revoked == 'foreign':
                    Membership.objects.filter(pk=self.member.pk).update(dealership=self.other)
                else:
                    Membership.objects.filter(pk=self.member.pk).delete()
                with self.assertRaises(PermissionDenied):
                    create_inline_vehicle(form, dealership=self.dealer, actor=self.user)
                self.assertFalse(Vehicle.objects.filter(stock_number='NEW').exists())
                self.assertFalse(AuditEvent.objects.exists())
                get_user_model().objects.filter(pk=self.user.pk).update(is_active=True)
                self.member, _ = Membership.objects.update_or_create(user=self.user, defaults={'dealership': self.dealer, 'role': 'owner'})
    def test_vehicle_create_and_edit_recheck_membership_before_validation(self):
        select = Membership.objects.select_for_update
        requests = [(reverse('vehicle_create'), self.data),
                    (reverse('vehicle_create'), self.data | {'year': ''}),
                    (reverse('vehicle_edit', args=[self.vehicle.pk]), self.data | {'stock_number': 'A-1', 'revision': 1}),
                    (reverse('vehicle_edit', args=[self.vehicle.pk]), self.data | {'stock_number': 'A-1', 'revision': 99})]
        for revoked in ('inactive', 'viewer', 'foreign', 'removed'):
            for url, payload in requests:
                with self.subTest(revoked=revoked, url=url):
                    def revoke():
                        if revoked == 'inactive':
                            get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
                        elif revoked == 'viewer':
                            Membership.objects.filter(pk=self.member.pk).update(role='viewer')
                        elif revoked == 'foreign':
                            Membership.objects.filter(pk=self.member.pk).update(dealership=self.other)
                        else:
                            Membership.objects.filter(pk=self.member.pk).delete()
                        return select()
                    with patch('inventory.views.Membership.objects.select_for_update', side_effect=revoke):
                        self.assertEqual(self.client.post(url, payload).status_code, 403)
                    self.vehicle.refresh_from_db()
                    self.assertEqual((Vehicle.objects.count(), AuditEvent.objects.count(), self.vehicle.revision, self.vehicle.model), (2, 0, 1, 'Local'))
    def test_no_membership_denied(self):
        self.member.delete()
        self.assertEqual(self.client.get(reverse("inventory")).status_code, 403)
    def test_tenant_isolation(self):
        self.assertNotContains(self.client.get(reverse("inventory")), "Foreign")
        self.assertEqual(self.client.get(reverse("vehicle_detail", args=[self.foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("vehicle_edit", args=[self.foreign.pk]), self.data).status_code, 404)
    def test_viewer_cannot_write(self):
        self.member.role = "viewer"
        self.member.save()
        self.assertEqual(self.client.get(reverse("inventory")).status_code, 200)
        self.assertEqual(self.client.post(reverse("vehicle_create"), self.data).status_code, 403)
        self.assertEqual(self.client.post(reverse("vehicle_edit", args=[self.vehicle.pk]), self.data).status_code, 403)
    def test_create_scoped_and_audited(self):
        response = self.client.post(reverse("vehicle_create"), {**self.data, "dealership": self.other.pk})
        self.assertEqual(response.status_code, 302)
        vehicle = Vehicle.objects.get(stock_number="NEW")
        self.assertEqual(vehicle.dealership, self.dealer)
        self.assertEqual(vehicle.total_cost, Decimal("100.30"))
        event = AuditEvent.objects.get(vehicle=vehicle)
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.changes["title_brand"]["after"], "rebuilt")
    def test_audit_failure_rolls_back_write(self):
        with patch("inventory.views.AuditEvent.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("vehicle_create"), self.data)
        self.assertFalse(Vehicle.objects.filter(stock_number="NEW").exists())
    def test_duplicate_stock_returns_validation_error(self):
        response = self.client.post(reverse("vehicle_create"), {**self.data, "stock_number": "a-1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vehicle.objects.filter(dealership=self.dealer).count(), 1)
    def test_negative_cost_rejected(self):
        response = self.client.post(reverse("vehicle_create"), {**self.data, "recon_cost": "-1"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vehicle.objects.filter(stock_number="NEW").exists())
    def test_stale_edit_preserves_input_without_overwriting(self):
        self.client.post(reverse("vehicle_edit", args=[self.vehicle.pk]), {**self.data, "revision": 1})
        response = self.client.post(reverse("vehicle_edit", args=[self.vehicle.pk]), {**self.data, "revision": 1, "model": "My unsaved changes"})
        self.assertContains(response, "My unsaved changes", status_code=409)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.model, "New")
        self.assertEqual(self.vehicle.revision, 2)
        self.assertEqual(AuditEvent.objects.filter(vehicle=self.vehicle).count(), 1)

    def test_edit_requires_revision(self):
        response = self.client.post(reverse("vehicle_edit", args=[self.vehicle.pk]), self.data)
        self.assertEqual(response.status_code, 200)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.model, "Local")
        self.assertFalse(AuditEvent.objects.exists())

    def test_invalid_form_preserves_entries_and_has_error_summary(self):
        response = self.client.post(reverse("vehicle_create"), {**self.data, "recon_cost": "-1", "notes": "Keep this draft"})
        self.assertContains(response, "Keep this draft")
        self.assertContains(response, "data-error-summary")
        self.assertFalse(Vehicle.objects.filter(stock_number="NEW").exists())
    def test_pages_render(self):
        for route in (reverse("today"), reverse("inventory"), reverse("vehicle_create"), reverse("vehicle_detail", args=[self.vehicle.pk]), reverse("vehicle_edit", args=[self.vehicle.pk])):
            self.assertEqual(self.client.get(route).status_code, 200)
    def test_post_requires_csrf(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("vehicle_create"), self.data).status_code, 403)

    def test_dashboard_filters_only_show_matching_dealership_vehicles(self):
        self.vehicle.title_received = False
        self.vehicle.save()
        sold = Vehicle.objects.create(dealership=self.dealer, stock_number="SOLD", year=2020, make="Test", model="Sold", status="sold")
        received = Vehicle.objects.create(dealership=self.dealer, stock_number="READY", year=2020, make="Test", model="Ready", title_received=True, title_brand="unbranded")
        response = self.client.get(reverse("inventory"), {"scope": "missing-title"})
        self.assertEqual(list(response.context["vehicles"]), [self.vehicle])
        response = self.client.get(reverse("inventory"), {"scope": "attention"})
        self.assertEqual(list(response.context["vehicles"]), [self.vehicle])
        response = self.client.get(reverse("inventory"), {"scope": "active"})
        self.assertEqual(set(response.context["vehicles"]), {self.vehicle, received})
        self.assertNotIn(sold, response.context["vehicles"])

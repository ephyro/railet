# SPDX-License-Identifier: MPL-2.0
"""Real exception-to-500 handling for marked private download views."""
import sys
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signals
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core.models import Dealership, Membership


@override_settings(
    DEBUG=False,
    SECURE_SSL_REDIRECT=False,
    ALLOWED_HOSTS=["testserver"],
    DEAL_FILES_DEMO_ENABLED=True,
    RECON_DEMO_ENABLED=True,
    DEMO_PACKETS_ENABLED=True,
)
class PrivateDownloadErrorTests(TestCase):
    def setUp(self):
        dealer = Dealership.objects.create(name="Synthetic private error dealer")
        user = get_user_model().objects.create_user(username="private-error-owner")
        Membership.objects.create(user=user, dealership=dealer, role="owner")
        self.client = Client(raise_request_exception=False)
        self.client.force_login(user)

    def test_unexpected_exceptions_are_reported_and_private_500s_not_cached(self):
        paths = (
            ("deal_file_download", [1, 1], "documents.views.get_object_or_404"),
            ("vehicle_invoice_download", [1, 1], "documents.invoice_views.get_object_or_404"),
            ("vehicle_acquisition_file_download", [1, 1], "documents.acquisition_views.get_object_or_404"),
            ("vehicle_photo_file", [1], "inventory.views.get_object_or_404"),
            ("vehicle_photo_thumbnail", [1], "inventory.views.get_object_or_404"),
            ("demo_packet_artifact", [1, 1], "documents.packet_views.get_object_or_404"),
        )
        caught = []

        def remember_exception(sender, **kwargs):
            caught.append(sys.exc_info()[1])

        signals.got_request_exception.connect(remember_exception, weak=False)
        self.addCleanup(signals.got_request_exception.disconnect, remember_exception)
        for route, args, target in paths:
            for method in (self.client.get, self.client.head):
                with self.subTest(route=route, method=method.__name__):
                    error = RuntimeError("synthetic private exception")
                    with patch(target, side_effect=error), self.assertLogs("django.request", level="ERROR") as logs:
                        response = method(reverse(route, args=args))
                    self.assertEqual(response.status_code, 500)
                    self.assertEqual(response["Cache-Control"], "private, no-store")
                    self.assertEqual(response["Pragma"], "no-cache")
                    self.assertEqual(response["Expires"], "0")
                    self.assertIs(caught[-1], error)
                    self.assertTrue(any("Internal Server Error" in entry for entry in logs.output))
                    self.assertTrue(any(record.exc_info and record.exc_info[1] is error for record in logs.records))
                    self.assertNotIn(b"synthetic private exception", response.content)

    def test_unmarked_route_errors_and_public_responses_are_not_changed(self):
        with patch("inventory.views.filter_context", side_effect=RuntimeError("synthetic public error")):
            with self.assertLogs("django.request", level="ERROR"):
                response = self.client.get(reverse("inventory"))
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("no-store", response.get("Cache-Control", ""))
        self.client.logout()
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)
        missing = self.client.get("/synthetic-missing-public-path/")
        self.assertEqual(missing.status_code, 404)
        self.assertNotIn("no-store", missing.get("Cache-Control", ""))

    def test_existing_private_statuses_and_gates_are_preserved(self):
        url = reverse("deal_file_download", args=[1, 1])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url).status_code, 405)
        self.client.logout()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        with override_settings(DEAL_FILES_DEMO_ENABLED=False):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Cache-Control"], "private, no-store")

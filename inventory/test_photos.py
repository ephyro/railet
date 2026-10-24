# SPDX-License-Identifier: MPL-2.0
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import AuditEvent, Dealership, Membership
from .models import Vehicle, VehiclePhoto
from .photos import MAX_BYTES, normalize_photo, add_photos


def photo_file(name="vehicle.jpg", color="blue", format="JPEG", exif=None):
    data = BytesIO()
    image = Image.new("RGB", (40, 20), color)
    kwargs = {"exif": exif} if exif is not None else {}
    image.save(data, format=format, **kwargs)
    image.close()
    return SimpleUploadedFile(name, data.getvalue(), content_type="image/jpeg")


class VehiclePhotoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealership.objects.create(name="Synthetic photo dealer")
        cls.other = Dealership.objects.create(name="Other photo dealer")
        cls.user = get_user_model().objects.create_user(username="photo-owner")
        cls.foreign_user = get_user_model().objects.create_user(username="photo-foreign")
        Membership.objects.create(user=cls.user, dealership=cls.dealer, role="owner")
        Membership.objects.create(user=cls.foreign_user, dealership=cls.other, role="owner")
        cls.vehicle = Vehicle.objects.create(dealership=cls.dealer, stock_number="PHOTO-1", year=2020, make="Synthetic", model="Car")
        cls.foreign = Vehicle.objects.create(dealership=cls.other, stock_number="FOREIGN", year=2020, make="Other", model="Car")

    def setUp(self):
        temporary = TemporaryDirectory()
        self.media = Path(temporary.name)
        self.addCleanup(temporary.cleanup)
        override = self.settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(self.user)

    def upload(self, files=None, vehicle=None):
        return self.client.post(reverse("vehicle_photo_upload", args=[(vehicle or self.vehicle).pk]), {"photos": files or [photo_file()]})

    def test_upload_normalizes_formats_orientation_and_strips_metadata(self):
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = "Synthetic private camera metadata"
        response = self.upload([photo_file(exif=exif), photo_file(name="pretend.svg", format="PNG")])
        self.assertEqual(response.status_code, 302)
        photos = list(VehiclePhoto.objects.order_by("pk"))
        self.assertEqual(len(photos), 2)
        self.assertTrue(photos[0].is_primary)
        self.assertFalse(photos[1].is_primary)
        with photos[0].image.open("rb") as stored:
            image = Image.open(stored)
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (20, 40))
            self.assertEqual(dict(image.getexif()), {})
            self.assertNotIn("icc_profile", image.info)
        with photos[0].thumbnail.open("rb") as stored:
            self.assertEqual(Image.open(stored).size, (320, 220))
        self.assertEqual(AuditEvent.objects.filter(vehicle=self.vehicle).count(), 1)
        with self.assertRaises(ValueError):
            _ = photos[0].image.url

    def test_downloads_are_authenticated_scoped_private_and_not_public_media(self):
        self.upload()
        photo = VehiclePhoto.objects.get()
        url = reverse("vehicle_photo_file", args=[photo.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertTrue(b"".join(response.streaming_content).startswith(b"\xff\xd8"))
        self.assertEqual(self.client.post(url).status_code, 405)
        self.client.force_login(self.foreign_user)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_cover_hide_and_restore_preserve_files_and_one_visible_cover(self):
        self.upload([photo_file(), photo_file(color="red")])
        first, second = list(VehiclePhoto.objects.order_by("pk"))
        self.client.post(reverse("vehicle_photo_action", args=[second.pk]), {"action": "cover"})
        self.assertEqual(VehiclePhoto.objects.get(is_primary=True).pk, second.pk)
        self.client.post(reverse("vehicle_photo_action", args=[second.pk]), {"action": "hide"})
        self.assertEqual(VehiclePhoto.objects.get(is_primary=True).pk, first.pk)
        second.refresh_from_db()
        self.assertIsNotNone(second.archived_at)
        self.assertTrue(second.image.storage.exists(second.image.name))
        Membership.objects.filter(user=self.user).update(role="viewer")
        self.assertEqual(self.client.get(reverse("vehicle_photo_file", args=[second.pk])).status_code, 404)
        Membership.objects.filter(user=self.user).update(role="owner")
        self.client.post(reverse("vehicle_photo_action", args=[second.pk]), {"action": "restore"})
        second.refresh_from_db()
        self.assertIsNone(second.archived_at)
        self.assertEqual(VehiclePhoto.objects.filter(is_primary=True, archived_at__isnull=True).count(), 1)

    def test_viewers_cannot_upload_or_change_photos(self):
        self.upload()
        photo = VehiclePhoto.objects.get()
        Membership.objects.filter(user=self.user).update(role="viewer")
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(self.client.post(reverse("vehicle_photo_action", args=[photo.pk]), {"action": "hide"}).status_code, 403)
        response = self.client.get(reverse("vehicle_photo_thumbnail", args=[photo.pk]))
        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)
        self.assertEqual(VehiclePhoto.objects.count(), 1)

    def test_other_dealership_upload_and_actions_are_denied(self):
        self.assertEqual(self.upload(vehicle=self.foreign).status_code, 404)
        self.upload()
        photo = VehiclePhoto.objects.get()
        self.client.force_login(self.foreign_user)
        self.assertEqual(self.client.post(reverse("vehicle_photo_action", args=[photo.pk]), {"action": "cover"}).status_code, 404)

    def test_rejects_svg_corruption_large_files_and_excessive_batches_without_writes(self):
        bad_batches = [
            [SimpleUploadedFile("fake.jpg", b"<svg><script>alert(1)</script></svg>", content_type="image/jpeg")],
            [SimpleUploadedFile("broken.png", b"not an image", content_type="image/png")],
            [SimpleUploadedFile("large.jpg", b"x" * (MAX_BYTES + 1), content_type="image/jpeg")],
            [photo_file() for _ in range(9)],
            [photo_file(), SimpleUploadedFile("bad.jpg", b"bad")],
        ]
        for files in bad_batches:
            with self.subTest(count=len(files)):
                response = self.upload(files)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["photo_form"].errors)
                self.assertFalse(VehiclePhoto.objects.exists())
                self.assertEqual(list(self.media.rglob("*.jpg")), [])

    def test_pixel_limits_and_supported_photo_formats(self):
        with patch("inventory.photos.MAX_PIXELS", 100):
            with self.assertRaisesMessage(ValidationError, "40 megapixels"):
                normalize_photo(photo_file())
        for format in ("JPEG", "PNG", "WEBP"):
            with self.subTest(format=format):
                full, thumbnail = normalize_photo(photo_file(format=format))
                self.assertTrue(full.startswith(b"\xff\xd8"))
                self.assertTrue(thumbnail.startswith(b"\xff\xd8"))

    def test_animated_photos_are_rejected(self):
        stream = BytesIO()
        first, second = Image.new("RGB", (20, 20), "blue"), Image.new("RGB", (20, 20), "red")
        first.save(stream, format="PNG", save_all=True, append_images=[second], duration=100, loop=0)
        first.close()
        second.close()
        response = self.upload([SimpleUploadedFile("animation.png", stream.getvalue(), content_type="image/png")])
        self.assertContains(response, "still photo")
        self.assertFalse(VehiclePhoto.objects.exists())

    def test_photo_limit_and_csrf(self):
        VehiclePhoto.objects.bulk_create([VehiclePhoto(vehicle=self.vehicle, image=f"synthetic/{index}.jpg", thumbnail=f"synthetic/{index}-thumb.jpg", created_by=self.user, is_primary=index == 0) for index in range(24)])
        self.assertContains(self.upload(), "24 visible photos")
        self.assertEqual(VehiclePhoto.objects.count(), 24)
        self.assertEqual(list(self.media.rglob("*.jpg")), [])
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("vehicle_photo_upload", args=[self.vehicle.pk]), {"photos": photo_file()}).status_code, 403)

    def test_audit_failure_rolls_back_rows_and_removes_written_files(self):
        with patch("inventory.photos.AuditEvent.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.upload()
        self.assertFalse(VehiclePhoto.objects.exists())
        self.assertEqual(list(self.media.rglob("*.jpg")), [])

    def test_has_photo_filter_and_stock_vin_picker_identity(self):
        self.upload()
        page = self.client.get(reverse("inventory"), {"filter_field": "photos", "filter_op": "eq", "filter_value": "true"})
        self.assertEqual(list(page.context["vehicles"]), [self.vehicle])
        self.assertContains(page, reverse("vehicle_photo_thumbnail", args=[VehiclePhoto.objects.get().pk]))
        picker = self.client.get(reverse("deal_create"))
        self.assertContains(picker, "Stock PHOTO-1")

    def test_draft_vehicle_thumbnails_are_prefetched(self):
        from customers.models import Customer
        from deals.models import DraftDeal
        self.upload()
        buyer = Customer.objects.create(dealership=self.dealer, first_name="Synthetic", last_name="Buyer")
        DraftDeal.objects.bulk_create([DraftDeal(dealership=self.dealer, buyer=buyer, vehicle=self.vehicle) for _ in range(25)])
        with CaptureQueriesContext(connection) as captured:
            page = self.client.get(reverse("deals"))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(sum('FROM "inventory_vehiclephoto"' in query["sql"] for query in captured), 1)


@skipUnless(connection.vendor == "postgresql", "Concurrent photo limit verification requires PostgreSQL")
class ConcurrentPhotoLimitTests(TransactionTestCase):
    def test_simultaneous_uploads_obey_the_per_vehicle_limit(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        override = self.settings(MEDIA_ROOT=temporary.name)
        override.enable()
        self.addCleanup(override.disable)
        dealer = Dealership.objects.create(name="Synthetic concurrent photo dealer")
        actor = get_user_model().objects.create_user(username="concurrent-photo-owner")
        vehicle = Vehicle.objects.create(dealership=dealer, stock_number="PHOTO-LIMIT", year=2020, make="Synthetic", model="Car")
        VehiclePhoto.objects.bulk_create([VehiclePhoto(vehicle=vehicle, created_by=actor, image=f"synthetic/{index}.jpg", thumbnail=f"synthetic/{index}-thumb.jpg", is_primary=index == 0) for index in range(23)])
        prepared = [normalize_photo(photo_file())]
        ready = Barrier(2)

        def upload():
            close_old_connections()
            try:
                ready.wait(timeout=20)
                try:
                    add_photos(vehicle, prepared, actor=actor)
                    return "added"
                except ValidationError:
                    return "full"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(upload) for _ in range(2)]
            results = [future.result(timeout=35) for future in futures]
        self.assertEqual(sorted(results), ["added", "full"])
        self.assertEqual(VehiclePhoto.objects.filter(archived_at__isnull=True).count(), 24)
        self.assertEqual(VehiclePhoto.objects.filter(is_primary=True, archived_at__isnull=True).count(), 1)
        self.assertEqual(len(list(Path(temporary.name).rglob("*.jpg"))), 2)
        self.assertEqual(AuditEvent.objects.count(), 1)

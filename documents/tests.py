# SPDX-License-Identifier: MPL-2.0
import tempfile
import uuid
import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Dealership, Membership
from customers.models import Customer
from deals.models import DraftDeal
from inventory.models import Vehicle

from .forms import SupportingFileUploadForm
from .models import DealFile, DealFileEvent
from .services import MAX_DEAL_BYTES, MAX_DEAL_FILES, MAX_FILE_BYTES


PDF_BYTES = b"%PDF-1.7\nSynthetic supporting file\n%%EOF\n"


class TemporaryDealFileStorageMixin:
    def setUp(self):
        self._media_temp = tempfile.TemporaryDirectory(prefix="railet-deal-files-")
        self._media_override = override_settings(MEDIA_ROOT=self._media_temp.name)
        self._media_override.enable()
        self._deal_file_storage = DealFile._meta.get_field("blob").storage
        self._deal_file_storage.__dict__.pop("location", None)
        super().setUp()

    def tearDown(self):
        try:
            super().tearDown()
        finally:
            self._media_override.disable()
            self._deal_file_storage.__dict__.pop("location", None)
            self._media_temp.cleanup()


@override_settings(DEAL_FILES_DEMO_ENABLED=True)
class SupportingFileWorkflowTests(TemporaryDealFileStorageMixin, TransactionTestCase):
    def setUp(self):
        super().setUp()
        user_model = get_user_model()
        self.dealer = Dealership.objects.create(name="Synthetic files dealer")
        self.other_dealer = Dealership.objects.create(name="Other synthetic files dealer")
        self.owner = user_model.objects.create_user(username="files-owner", password="test-only")
        self.staff = user_model.objects.create_user(username="files-staff", password="test-only")
        self.viewer = user_model.objects.create_user(username="files-viewer", password="test-only")
        self.foreign_user = user_model.objects.create_user(username="files-foreign", password="test-only")
        Membership.objects.create(user=self.owner, dealership=self.dealer, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.staff, dealership=self.dealer, role=Membership.Role.STAFF)
        Membership.objects.create(user=self.viewer, dealership=self.dealer, role=Membership.Role.VIEWER)
        Membership.objects.create(user=self.foreign_user, dealership=self.other_dealer, role=Membership.Role.OWNER)
        self.vehicle = Vehicle.objects.create(
            dealership=self.dealer,
            stock_number="FILES-SALE",
            year=2021,
            make="Synthetic",
            model="Sale vehicle",
        )
        self.buyer = Customer.objects.create(
            dealership=self.dealer,
            first_name="Synthetic",
            last_name="Buyer",
        )
        self.deal = DraftDeal.objects.create(
            dealership=self.dealer,
            vehicle=self.vehicle,
            buyer=self.buyer,
        )
        self.foreign_vehicle = Vehicle.objects.create(
            dealership=self.other_dealer,
            stock_number="PRIVATE-STOCK",
            year=2020,
            make="Private",
            model="Foreign vehicle",
        )
        self.foreign_buyer = Customer.objects.create(
            dealership=self.other_dealer,
            first_name="Private",
            last_name="Buyer",
        )
        self.foreign_deal = DraftDeal.objects.create(
            dealership=self.other_dealer,
            vehicle=self.foreign_vehicle,
            buyer=self.foreign_buyer,
        )
        self.client.force_login(self.owner)
        self.files_url = reverse("deal_files", args=[self.deal.pk])

    def upload_data(self, *, title="Synthetic attachment", key=None, pdf=PDF_BYTES, filename="source.pdf", content_type="application/pdf"):
        return {
            "title": title,
            "upload_key": str(key or uuid.uuid4()),
            "pdf_file": SimpleUploadedFile(filename, pdf, content_type=content_type),
        }

    def upload(self, **kwargs):
        return self.client.post(self.files_url, self.upload_data(**kwargs))

    def create_stored_file(self, *, deal=None, title="Synthetic stored file", content=PDF_BYTES, archived_at=None, byte_size=None, actor=None, key=None):
        file_key = key or uuid.uuid4()
        storage_name = self._deal_file_storage.save(
            f"deal-files/{uuid.uuid4()}.pdf",
            ContentFile(content),
        )
        deal_file = DealFile.objects.create(
            deal=deal or self.deal,
            title=title,
            blob=storage_name,
            sha256=hashlib.sha256(content).hexdigest(),
            byte_size=len(content) if byte_size is None else byte_size,
            created_by=actor or self.owner,
            upload_key=file_key,
            archived_at=archived_at,
        )
        return deal_file

    def action_post(self, deal_file, *, action="archive", reason="Synthetic retention note", client=None):
        prefix = f"file-{deal_file.pk}-{action}"
        data = {f"{prefix}-action": action}
        if action == "archive":
            data[f"{prefix}-reason"] = reason
        client = client or self.client
        return client.post(
            reverse("deal_file_action", args=[deal_file.deal_id, deal_file.pk]),
            data,
        )

    def test_cross_dealer_scope_anonymous_and_wrong_methods(self):
        own_file = self.create_stored_file(title="Local title")
        foreign_file = self.create_stored_file(
            deal=self.foreign_deal,
            title="Foreign private title",
        )
        self.assertEqual(self.client.get(reverse("deal_files", args=[self.foreign_deal.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("deal_file_download", args=[self.deal.pk, foreign_file.pk])).status_code, 404)
        response = self.client.get(self.files_url)
        self.assertContains(response, "Local title")
        self.assertNotContains(response, "Foreign private title")

        anonymous = Client()
        login = anonymous.get(self.files_url)
        self.assertEqual(login.status_code, 302)
        self.assertIn("private", login["Cache-Control"])

        self.assertEqual(self.client.put(self.files_url).status_code, 405)
        self.assertEqual(self.client.get(reverse("deal_file_action", args=[self.deal.pk, own_file.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse("deal_file_download", args=[self.deal.pk, own_file.pk])).status_code, 405)

    def test_demo_gate_fails_closed_for_list_upload_action_and_download_methods(self):
        deal_file = self.create_stored_file(title="Gated file")
        with override_settings(DEAL_FILES_DEMO_ENABLED=False):
            responses = [
                self.client.get(self.files_url),
                self.client.post(self.files_url, self.upload_data()),
                self.client.post(reverse("deal_file_action", args=[self.deal.pk, deal_file.pk]), {}),
                self.client.get(reverse("deal_file_download", args=[self.deal.pk, deal_file.pk])),
                self.client.head(reverse("deal_file_download", args=[self.deal.pk, deal_file.pk])),
            ]
        for response in responses:
            self.assertEqual(response.status_code, 404)
            self.assertIn("no-store", response["Cache-Control"])

    def test_private_no_store_for_page_redirect_errors_and_download_headers(self):
        page = self.client.get(self.files_url)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page["Cache-Control"], "private, no-store")
        self.assertContains(page, "Synthetic development only")
        self.assertContains(page, "Files stay with this draft deal")
        self.assertContains(page, "vehicle-form.js")

        missing = self.client.get(reverse("deal_file_download", args=[self.deal.pk, 999999]))
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing["Cache-Control"], "private, no-store")

        deal_file = self.create_stored_file(title="Attachment title")
        response = self.client.get(reverse("deal_file_download", args=[self.deal.pk, deal_file.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/octet-stream")
        self.assertEqual(response["Content-Disposition"], f'attachment; filename="deal-file-{deal_file.pk}.pdf"')
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Content-Security-Policy"], "sandbox")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertNotIn("deal-files/", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), PDF_BYTES)
        response.close()

    def test_upload_uses_pdf_bytes_not_original_filename_or_declared_content_type(self):
        title = "<script>alert('synthetic')</script>"
        response = self.upload(title=title, filename="private-source-name.html", content_type="text/html")
        self.assertEqual(response.status_code, 302)
        deal_file = DealFile.objects.get()
        self.assertEqual(deal_file.title, title)
        self.assertEqual(deal_file.blob.name.rsplit("/", 1)[-1].endswith(".pdf"), True)
        self.assertNotIn("private-source-name", deal_file.blob.name)
        self.assertEqual(deal_file.byte_size, len(PDF_BYTES))

        page = self.client.get(self.files_url)
        self.assertContains(page, "&lt;script&gt;alert(&#x27;synthetic&#x27;)&lt;/script&gt;")
        self.assertNotContains(page, "<script>alert('synthetic')</script>")
        self.assertContains(page, 'accept=".pdf,application/pdf"')
        self.assertNotContains(page, "private-source-name")

    def test_empty_spoof_and_incomplete_pdf_files_are_rejected(self):
        bad_files = [
            b"",
            b"<html><body>not a pdf</body></html>",
            b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            b"%PDF-1.7\nmissing end marker",
        ]
        for index, content in enumerate(bad_files):
            with self.subTest(index=index):
                response = self.upload(
                    title=f"Bad synthetic {index}",
                    filename="looks-like-a-pdf.pdf",
                    pdf=content,
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Review this upload")
                self.assertEqual(DealFile.objects.count(), 0)
                self.assertEqual(DealFileEvent.objects.count(), 0)

    def test_actual_file_size_is_bounded_and_eight_mib_is_allowed(self):
        too_large = b"%PDF-" + b"x" * (MAX_FILE_BYTES - len(b"%PDF-") + 1)
        response = self.upload(title="Too large", pdf=too_large)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no larger than 8 MiB")
        self.assertEqual(DealFile.objects.count(), 0)

        eof = b"%%EOF\n"
        exact_limit = b"%PDF-" + b"x" * (MAX_FILE_BYTES - len(b"%PDF-") - len(eof)) + eof
        self.assertEqual(len(exact_limit), MAX_FILE_BYTES)
        response = self.upload(title="At size limit", pdf=exact_limit)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DealFile.objects.get().byte_size, MAX_FILE_BYTES)

    def test_title_and_upload_key_survive_validation_and_key_mismatch_is_actionable(self):
        key = uuid.uuid4()
        first = self.upload(title="Original title", key=key)
        self.assertEqual(first.status_code, 302)
        self.client.get(self.files_url)

        mismatch = self.upload(title="Changed title", key=key)
        self.assertEqual(mismatch.status_code, 200)
        self.assertContains(mismatch, "already linked to a different file or title")
        self.assertContains(mismatch, 'name="title" value="Changed title"')
        self.assertContains(mismatch, f'name="upload_key" value="{key}"')
        self.assertContains(mismatch, "choose the PDF again after an error")
        self.assertContains(mismatch, "Start a fresh upload with a new submission key")
        count = DealFileEvent.objects.count()
        different_bytes = self.upload(title="Original title", key=key, pdf=b"%PDF-1.7\nOther\n%%EOF\n")
        self.assertEqual(different_bytes.status_code, 200)
        self.assertContains(different_bytes, "already linked to a different file or title")
        self.assertEqual(DealFile.objects.count(), 1)
        self.assertEqual(DealFileEvent.objects.count(), count)

    def test_same_key_retry_returns_existing_archived_file_without_new_blob_or_event(self):
        key = uuid.uuid4()
        response = self.upload(title="Idempotent title", key=key)
        self.assertEqual(response.status_code, 302)
        deal_file = DealFile.objects.get()
        stored_name = deal_file.blob.name
        self.assertEqual(DealFileEvent.objects.filter(file=deal_file).count(), 1)

        archived = self.action_post(deal_file, action="archive", reason="Duplicate copy retained for history")
        self.assertEqual(archived.status_code, 302)
        deal_file.refresh_from_db()
        archived_at = deal_file.archived_at
        event_count = DealFileEvent.objects.filter(file=deal_file).count()
        self.assertEqual(event_count, 2)

        retry = self.upload(title="Idempotent title", key=key)
        self.assertEqual(retry.status_code, 302)
        deal_file.refresh_from_db()
        self.assertEqual(deal_file.archived_at, archived_at)
        self.assertEqual(deal_file.blob.name, stored_name)
        self.assertTrue(self._deal_file_storage.exists(stored_name))
        self.assertEqual(DealFile.objects.count(), 1)
        self.assertEqual(DealFileEvent.objects.filter(file=deal_file).count(), event_count)

    def test_upload_and_event_failure_roll_back_database_and_remove_new_blob(self):
        with patch("documents.services.DealFileEvent.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.upload(title="Rollback file")

        self.assertEqual(DealFile.objects.count(), 0)
        self.assertEqual(DealFileEvent.objects.count(), 0)
        try:
            _, names = self._deal_file_storage.listdir("deal-files")
        except FileNotFoundError:
            names = []
        self.assertEqual(names, [])

    def test_retained_quotas_include_archived_files_and_bytes(self):
        for index in range(MAX_DEAL_FILES):
            DealFile.objects.create(
                deal=self.deal,
                title=f"Archived quota {index}",
                blob=f"deal-files/nonexistent-{index}.pdf",
                sha256="a" * 64,
                byte_size=1,
                created_by=self.owner,
                archived_at=timezone.now(),
                upload_key=uuid.uuid4(),
            )
        count_limit = self.upload(title="Over count quota")
        self.assertEqual(count_limit.status_code, 200)
        self.assertContains(count_limit, "already has 100 retained files")
        self.assertEqual(DealFile.objects.count(), MAX_DEAL_FILES)

    def test_total_retained_bytes_quota_includes_archived_files(self):
        DealFile.objects.create(
            deal=self.deal,
            title="Archived byte quota",
            blob="deal-files/nonexistent-large.pdf",
            sha256="b" * 64,
            byte_size=MAX_DEAL_BYTES,
            created_by=self.owner,
            archived_at=timezone.now(),
            upload_key=uuid.uuid4(),
        )
        byte_limit = self.upload(title="Over byte quota")
        self.assertEqual(byte_limit.status_code, 200)
        self.assertContains(byte_limit, "exceed 100 MiB")
        self.assertEqual(DealFile.objects.count(), 1)

    def test_archive_restore_are_reasoned_idempotent_and_retain_original_bytes(self):
        response = self.upload(title="Archive workflow file")
        self.assertEqual(response.status_code, 302)
        deal_file = DealFile.objects.get()
        name, digest, size = deal_file.blob.name, deal_file.sha256, deal_file.byte_size
        active_page = self.client.get(self.files_url)
        self.assertNotRegex(
            active_page.content.decode(),
            r'<details class="file-archive-disclosure"[^>]*\bopen\b',
        )
        with self._deal_file_storage.open(name, "rb") as stored:
            original = stored.read()

        missing_reason = self.action_post(deal_file, action="archive", reason="")
        self.assertEqual(missing_reason.status_code, 200)
        self.assertContains(missing_reason, "Enter a reason to archive this file")
        self.assertContains(missing_reason, '<details class="file-archive-disclosure" open')
        self.assertIsNone(DealFile.objects.get(pk=deal_file.pk).archived_at)
        self.assertEqual(DealFileEvent.objects.filter(file=deal_file).count(), 1)

        archive = self.action_post(deal_file, action="archive", reason="Temporary duplicate retained")
        self.assertEqual(archive.status_code, 302)
        deal_file.refresh_from_db()
        self.assertIsNotNone(deal_file.archived_at)
        self.assertEqual(DealFileEvent.objects.filter(file=deal_file).count(), 2)
        archived_page = self.client.get(self.files_url)
        self.assertContains(archived_page, "Temporary duplicate retained")
        self.assertContains(
            archived_page,
            f'href="{reverse("deal_file_download", args=[self.deal.pk, deal_file.pk])}">Download PDF</a>',
        )

        repeated_archive = self.action_post(deal_file, action="archive", reason="Repeated state")
        self.assertEqual(repeated_archive.status_code, 302)
        self.assertEqual(DealFileEvent.objects.filter(file=deal_file).count(), 2)

        restore = self.action_post(deal_file, action="restore")
        self.assertEqual(restore.status_code, 302)
        deal_file.refresh_from_db()
        self.assertIsNone(deal_file.archived_at)
        self.assertEqual((deal_file.blob.name, deal_file.sha256, deal_file.byte_size), (name, digest, size))
        self.assertEqual(DealFileEvent.objects.filter(file=deal_file).count(), 3)
        with self._deal_file_storage.open(name, "rb") as stored:
            self.assertEqual(stored.read(), original)

        repeated_restore = self.action_post(deal_file, action="restore")
        self.assertEqual(repeated_restore.status_code, 302)
        self.assertEqual(DealFileEvent.objects.filter(file=deal_file).count(), 3)

    def test_viewer_sees_active_only_and_cannot_download_archived_get_or_head(self):
        active = self.create_stored_file(title="Active synthetic file")
        archived = self.create_stored_file(title="Archived synthetic file")
        self.action_post(archived, action="archive", reason="Synthetic archive reason")
        self.client.force_login(self.viewer)

        response = self.client.get(self.files_url)
        self.assertContains(response, "Active synthetic file")
        self.assertNotContains(response, "Archived synthetic file")
        self.assertNotContains(response, reverse("deal_file_action", args=[self.deal.pk, active.pk]))
        for method in (self.client.get, self.client.head):
            hidden = method(reverse("deal_file_download", args=[self.deal.pk, archived.pk]))
            self.assertEqual(hidden.status_code, 404)
            self.assertEqual(hidden["Cache-Control"], "private, no-store")

    def test_viewers_cannot_upload_or_archive_and_csrf_is_required(self):
        deal_file = self.create_stored_file(title="No viewer action")
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.post(self.files_url, self.upload_data()).status_code, 403)
        self.assertEqual(self.action_post(deal_file).status_code, 403)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        self.assertEqual(csrf_client.post(self.files_url, self.upload_data()).status_code, 403)
        prefix = f"file-{deal_file.pk}-archive"
        action_url = reverse("deal_file_action", args=[self.deal.pk, deal_file.pk])
        self.assertEqual(
            csrf_client.post(action_url, {f"{prefix}-action": "archive", f"{prefix}-reason": "test"}).status_code,
            403,
        )

    def test_missing_storage_blob_returns_404_without_download_event(self):
        missing = DealFile.objects.create(
            deal=self.deal,
            title="Missing synthetic blob",
            blob="deal-files/missing.pdf",
            sha256="c" * 64,
            byte_size=len(PDF_BYTES),
            created_by=self.owner,
            upload_key=uuid.uuid4(),
        )
        for method in (self.client.get, self.client.head):
            response = method(reverse("deal_file_download", args=[self.deal.pk, missing.pk]))
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertFalse(DealFileEvent.objects.filter(file=missing, action=DealFileEvent.Action.DOWNLOAD).exists())

    def test_download_audit_failure_closes_open_handle_and_fails_closed(self):
        deal_file = self.create_stored_file(title="Audit failure target")
        original_open = self._deal_file_storage.open
        opened = []

        def capture_open(name, mode="rb"):
            handle = original_open(name, mode)
            opened.append(handle)
            return handle

        with patch.object(self._deal_file_storage, "open", side_effect=capture_open):
            with patch("documents.views.DealFileEvent.objects.create", side_effect=RuntimeError("audit unavailable")):
                with self.assertRaises(RuntimeError):
                    self.client.get(reverse("deal_file_download", args=[self.deal.pk, deal_file.pk]))
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].closed)
        self.assertFalse(DealFileEvent.objects.filter(file=deal_file, action=DealFileEvent.Action.DOWNLOAD).exists())

    def test_successful_get_and_head_are_audited_with_actor_and_file(self):
        deal_file = self.create_stored_file(title="Audit target")
        get_response = self.client.get(reverse("deal_file_download", args=[self.deal.pk, deal_file.pk]))
        self.assertEqual(get_response.status_code, 200)
        get_response.close()
        head_response = self.client.head(reverse("deal_file_download", args=[self.deal.pk, deal_file.pk]))
        self.assertEqual(head_response.status_code, 200)
        self.assertEqual(head_response.content, b"")
        events = DealFileEvent.objects.filter(file=deal_file, action=DealFileEvent.Action.DOWNLOAD)
        self.assertEqual(events.count(), 2)
        self.assertTrue(all(event.actor == self.owner and event.file_id == deal_file.pk and event.created_at for event in events))


@skipUnless(connection.vendor == "postgresql", "Concurrent upload locking requires PostgreSQL")
@override_settings(DEAL_FILES_DEMO_ENABLED=True)
class ConcurrentSupportingFileUploadTests(TemporaryDealFileStorageMixin, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.dealer = Dealership.objects.create(name="Synthetic concurrent files dealer")
        self.user = get_user_model().objects.create_user(username="files-concurrent", password="test-only")
        Membership.objects.create(user=self.user, dealership=self.dealer, role=Membership.Role.OWNER)
        vehicle = Vehicle.objects.create(
            dealership=self.dealer,
            stock_number="CONCURRENT-SALE",
            year=2022,
            make="Synthetic",
            model="Concurrent sale",
        )
        buyer = Customer.objects.create(dealership=self.dealer, first_name="Synthetic", last_name="Buyer")
        self.deal = DraftDeal.objects.create(dealership=self.dealer, vehicle=vehicle, buyer=buyer)
        self.user_id = self.user.pk

    def test_simultaneous_same_key_uploads_create_one_file_one_blob_and_one_event(self):
        key = str(uuid.uuid4())
        barrier = Barrier(2)
        url = reverse("deal_files", args=[self.deal.pk])

        def submit():
            close_old_connections()
            try:
                client = Client()
                client.force_login(get_user_model().objects.get(pk=self.user_id))
                barrier.wait(timeout=10)
                response = client.post(
                    url,
                    {
                        "title": "Same synthetic file",
                        "upload_key": key,
                        "pdf_file": SimpleUploadedFile("same.pdf", PDF_BYTES, content_type="application/pdf"),
                    },
                )
                return response.status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = [future.result(timeout=30) for future in [pool.submit(submit), pool.submit(submit)]]

        self.assertEqual(statuses, [302, 302])
        self.assertEqual(DealFile.objects.filter(deal=self.deal, upload_key=key).count(), 1)
        deal_file = DealFile.objects.get(deal=self.deal, upload_key=key)
        self.assertEqual(DealFileEvent.objects.filter(file=deal_file, action=DealFileEvent.Action.UPLOAD).count(), 1)
        _, names = self._deal_file_storage.listdir("deal-files")
        self.assertEqual(len(names), 1)

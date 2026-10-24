# SPDX-License-Identifier: MPL-2.0
"""Independent overseer checks of authorization ordering and storage/DB boundaries."""
import uuid
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from core.models import Dealership, Membership
from customers.models import Customer
from inventory.models import Vehicle
from deals.models import DraftDeal, DealEvent
from . import tests as file_scenarios
from .models import DealFile, DealFileEvent
from .services import upload_deal_file, change_deal_file_state


@override_settings(DEAL_FILES_DEMO_ENABLED=True)
class SupportingFileBoundaryTests(file_scenarios.TemporaryDealFileStorageMixin, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.dealer = Dealership.objects.create(name='Synthetic boundary dealer')
        self.foreign = Dealership.objects.create(name='Synthetic other dealer')
        self.user = get_user_model().objects.create_user(username='files-boundary-staff')
        self.viewer = get_user_model().objects.create_user(username='files-boundary-viewer')
        Membership.objects.create(user=self.user, dealership=self.dealer, role='staff')
        Membership.objects.create(user=self.viewer, dealership=self.dealer, role='viewer')
        vehicle = Vehicle.objects.create(dealership=self.dealer, stock_number='BOUNDARY', year=2020, make='Synthetic', model='Vehicle')
        buyer = Customer.objects.create(dealership=self.dealer, first_name='Synthetic', last_name='Buyer')
        self.deal = DraftDeal.objects.create(dealership=self.dealer, vehicle=vehicle, buyer=buyer, sale_price='10000.50')
        self.other_deal = DraftDeal.objects.create(dealership=self.foreign, vehicle=vehicle, buyer=buyer)
        self.client.force_login(self.user)

    def upload(self, **changes):
        args = dict(deal_id=self.deal.pk, dealership_id=self.dealer.pk, actor=self.user,
                    title='Synthetic supporting PDF', upload_key=uuid.uuid4(), pdf_bytes=file_scenarios.PDF_BYTES)
        args.update(changes)
        return upload_deal_file(**args)[0]

    def test_denied_get_and_head_never_open_storage(self):
        own = self.upload()
        other = self.upload(deal_id=self.other_deal.pk, dealership_id=self.foreign.pk)
        change_deal_file_state(deal_id=self.deal.pk, dealership_id=self.dealer.pk,
            file_id=own.pk, actor=self.user, action='archive', reason='Synthetic archive')
        with patch.object(self._deal_file_storage, 'open', side_effect=AssertionError('Unauthorized storage access')) as opened:
            for method in (self.client.get, self.client.head):
                self.assertEqual(method(reverse('deal_file_download',args=[self.deal.pk,other.pk])).status_code,404)
                self.assertEqual(method(reverse('deal_file_download',args=[self.other_deal.pk,other.pk])).status_code,404)
            self.client.force_login(self.viewer)
            for method in (self.client.get, self.client.head):
                self.assertEqual(method(reverse('deal_file_download',args=[self.deal.pk,own.pk])).status_code,404)
            with override_settings(DEAL_FILES_DEMO_ENABLED=False):
                self.client.logout()
                self.assertEqual(self.client.head(reverse('deal_file_download',args=[self.deal.pk,own.pk])).status_code,404)
            opened.assert_not_called()

    def test_commit_failure_removes_new_blob_and_database_rows(self):
        with patch.object(connection, 'commit', side_effect=DatabaseError('Synthetic failed commit')):
            with self.assertRaises(DatabaseError):
                self.upload()
        self.assertFalse(DealFile.objects.exists())
        self.assertFalse(DealFileEvent.objects.exists())
        self.assertEqual(self._deal_file_storage.listdir('deal-files')[1], [])

    def test_nested_transaction_is_rejected_before_storage_write(self):
        with transaction.atomic():
            with self.assertRaises(RuntimeError):
                self.upload()
        self.assertFalse(DealFile.objects.exists())
        self.assertFalse(self._deal_file_storage.exists('deal-files'))

    def test_archive_audit_failure_rolls_back_state_without_altering_bytes(self):
        stored = self.upload()
        with patch('documents.services.DealFileEvent.objects.create',side_effect=RuntimeError('Synthetic failed audit')):
            with self.assertRaises(RuntimeError):
                change_deal_file_state(deal_id=self.deal.pk,dealership_id=self.dealer.pk,
                    file_id=stored.pk,actor=self.user,action='archive',reason='Synthetic attempt')
        stored.refresh_from_db()
        self.assertIsNone(stored.archived_at)
        with stored.blob.open('rb') as stream:
            self.assertEqual(stream.read(),file_scenarios.PDF_BYTES)
        self.assertEqual(DealFileEvent.objects.count(),1)

    def test_file_actions_leave_deal_financial_revision_and_history_untouched(self):
        before = DraftDeal.objects.filter(pk=self.deal.pk).values().get()
        stored = self.upload()
        for action in ('archive','restore'):
            change_deal_file_state(deal_id=self.deal.pk,dealership_id=self.dealer.pk,
                file_id=stored.pk,actor=self.user,action=action,reason='Synthetic review')
        response = self.client.head(reverse('deal_file_download',args=[self.deal.pk,stored.pk]))
        self.assertEqual(response.status_code,200)
        self.assertEqual(DraftDeal.objects.filter(pk=self.deal.pk).values().get(),before)
        self.assertFalse(DealEvent.objects.exists())

# SPDX-License-Identifier: MPL-2.0
import json
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.utils import timezone
from core.models import Membership
from customers.models import Customer
from inventory.models import Vehicle
from finance import test_completed_handoff as fixtures
from .export import DealExportError, FORMAT_VERSION, export_deals
from .models import (DraftDeal, DraftFinanceProposal, DraftTradeIn, DealEvent,
                     DealFollowUp, FollowUpEvent, DemoDealCompletion)


@override_settings(DEBUG=True, DEMO_COMPLETION_ENABLED=True, DEMO_PACKETS_ENABLED=True)
class DealExportTests(TestCase):
    source = fixtures.CompletedHandoffTests.source

    def setUp(self):
        fixtures.CompletedHandoffTests.setUp(self)
        self.owner = get_user_model().objects.create_user('deal-export-owner')
        Membership.objects.create(user=self.owner, dealership=self.dealer, role='owner')
        # An independent open deal carries archived trade and follow-up history.
        self.open_deal = DraftDeal.objects.create(dealership=self.dealer, vehicle=self.vehicle,
            buyer=self.buyer, sale_price=Decimal('1234.50'), notes='=Synthetic internal note')
        self.trade = DraftTradeIn.objects.create(deal=self.open_deal, vin='SYNTHETIC-TRADE',
            title_brand='unknown', archived_at=timezone.now())
        self.followup = DealFollowUp.objects.create(deal=self.open_deal, title='Synthetic call',
            created_by=self.user, assigned_to=None, due_on=None)
        self.follow_event = FollowUpEvent.objects.create(follow_up=self.followup, actor=self.user,
            action='completed', snapshot={'prior': None, 'reason': 'synthetic correction'})
        self.history = DealEvent.objects.create(deal=self.open_deal, actor=self.user,
            snapshot={'schema_version': 2, 'action': 'trade_removed', 'unknown': None})
        foreign_vehicle = Vehicle.objects.create(dealership=self.other, stock_number='FOREIGN-PRIVATE', year=2020, make='Synthetic', model='Foreign')
        foreign_customer = Customer.objects.create(dealership=self.other, first_name='Foreign synthetic')
        self.foreign = DraftDeal.objects.create(dealership=self.other, vehicle=foreign_vehicle, buyer=foreign_customer, notes='FOREIGN-PRIVATE')
        DealEvent.objects.create(deal=self.foreign, actor=self.users['foreign'], snapshot={'detail':'FOREIGN-PRIVATE-EVENT'})

    def export(self, actor=None, dealership_id=None):
        return export_deals(dealership_id=dealership_id or self.dealer.pk, actor=actor or self.owner)

    def test_all_owned_models_and_fields_export_with_frozen_references(self):
        result = self.export()
        self.assertEqual(result['format'], FORMAT_VERSION)
        self.assertEqual({x['id'] for x in result['deals']}, {self.deal.pk, self.open_deal.pk})
        for model, key in ((DraftDeal, 'deals'), (DraftFinanceProposal, 'finance_proposals'),
                           (DraftTradeIn, 'trades'), (DealEvent, 'deal_events'),
                           (DealFollowUp, 'follow_ups'), (FollowUpEvent, 'follow_up_events')):
            expected_fields = {field.attname for field in model._meta.concrete_fields}
            self.assertTrue(result[key], key)
            self.assertEqual(set(result[key][0]), expected_fields, key)
        trade = result['trades'][0]
        self.assertEqual(trade['title_brand'], 'unknown')
        self.assertIsNotNone(trade['archived_at'])
        self.assertIsNone(trade['odometer_reading'])
        self.assertEqual(result['follow_ups'][0]['created_by_id'], self.user.pk)
        self.assertIsNone(result['follow_ups'][0]['due_on'])
        self.assertEqual(result['follow_up_events'][0]['snapshot'], self.follow_event.snapshot)
        self.assertIn(self.history.snapshot, [event['snapshot'] for event in result['deal_events']])
        completion = result['completions'][0]
        record = DemoDealCompletion.objects.get(deal=self.deal)
        fields = {field.attname for field in DemoDealCompletion._meta.concrete_fields}
        self.assertEqual(set(completion), fields | {'packet_template_version'})
        self.assertEqual(completion['packet_id'], record.packet_id)
        self.assertEqual(completion['packet_template_version'], record.packet.template_version)
        self.assertEqual(completion['metadata'], record.metadata)
        self.assertEqual(completion['review_sha256'], record.review_sha256)
        self.assertNotIn('FOREIGN-PRIVATE', json.dumps(result))
        self.assertIn('not guaranteed', result['consistency'])
        self.assertIn('document bytes', result['scope'])
        self.assertEqual(next(d for d in result['deals'] if d['id'] == self.open_deal.pk)['sale_price'], '1234.50')

    def test_owner_scope_active_membership_and_synthetic_gates(self):
        for actor in (self.user, self.users['viewer'], self.users['foreign'], AnonymousUser()):
            with self.subTest(actor=str(actor)), self.assertRaises(PermissionDenied):
                self.export(actor=actor)
        with self.assertRaises(PermissionDenied):
            self.export(dealership_id=self.other.pk)
        for settings in ({'DEBUG': False}, {'DEMO_COMPLETION_ENABLED': False}, {'DEMO_PACKETS_ENABLED': False}):
            with self.subTest(settings=settings), override_settings(**settings), self.assertRaises(PermissionDenied):
                self.export()
        self.owner.is_active = False
        self.owner.save(update_fields=['is_active'])
        with self.assertRaises(PermissionDenied):
            self.export()

    def test_row_and_byte_limits_fail_without_partial_export(self):
        for name in ('MAX_DEALS', 'MAX_CHILD_ROWS', 'MAX_BYTES'):
            with self.subTest(limit=name), patch('deals.export.' + name, 0), self.assertRaises(DealExportError):
                self.export()

    def test_mismatched_out_of_scope_parent_fails_closed(self):
        DraftDeal.objects.filter(pk=self.open_deal.pk).update(buyer_id=self.foreign.buyer_id)
        with self.assertRaises(DealExportError):
            self.export()

    def test_snapshot_uses_historical_completion_not_current_profiles(self):
        saved = self.export()['completions'][0]
        self.buyer.first_name = 'Changed current'; self.buyer.save()
        self.vehicle.model = 'Changed current'; self.vehicle.save()
        self.assertEqual(saved, self.export()['completions'][0])

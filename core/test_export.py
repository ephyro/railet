# SPDX-License-Identifier: MPL-2.0
import json
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.utils import timezone
from .export import FORMAT_VERSION, FoundationExportTooLarge, export_foundation
from .models import Dealership, DealershipExportEvent, Membership, SavedView


@override_settings(DEBUG=True)
class FoundationExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealership.objects.create(name='Synthetic foundation dealer')
        cls.other = Dealership.objects.create(name='Foreign foundation dealer')
        cls.users = {}
        cls.memberships = {}
        for label, role, dealer, active in [
            ('owner', 'owner', cls.dealer, True),
            ('staff', 'staff', cls.dealer, True),
            ('viewer', 'viewer', cls.dealer, True),
            ('inactive_staff', 'staff', cls.dealer, False),
            ('foreign', 'owner', cls.other, True),
        ]:
            user = get_user_model().objects.create_user(
                username='found-' + label,
                password='SUPER-SECRET-PASSWORD-' + label,
                email=f'{label}-private@example.invalid',
            )
            if not active:
                user.is_active = False
                user.save(update_fields=['is_active'])
            m = Membership.objects.create(user=user, dealership=dealer, role=role)
            cls.users[label] = user
            cls.memberships[label] = m

        SavedView.objects.create(
            dealership=cls.dealer, owner=cls.users['owner'],
            resource='inventory', name='PRIVATE-SAVED-VIEW', parameters={'q': ['secret']},
        )
        Session.objects.create(
            session_key='private-session-key-1234567890',
            session_data='private-session-payload',
            expire_date=timezone.now(),
        )

    def export(self, actor=None, dealer=None):
        return export_foundation(dealership_id=(dealer or self.dealer).pk, actor=actor or self.users['owner'])

    def test_dealership_and_member_provenance_exported_without_secrets_or_saved_views(self):
        data = self.export()
        serialized = json.dumps(data)
        self.assertEqual(data['format'], FORMAT_VERSION)
        self.assertTrue(data['synthetic_only'])
        self.assertEqual(data['dealership_id'], self.dealer.pk)
        self.assertEqual(data['exported_by_user_id'], self.users['owner'].pk)
        self.assertEqual(data['dealership'], {'id': self.dealer.pk, 'name': 'Synthetic foundation dealer'})
        self.assertIn('personal saved views', data['scope'])
        self.assertIn('Not a complete dealership backup', data['scope'])

        # All same-dealership memberships (including inactive staff provenance) are included in pk order
        expected_ids = [
            self.memberships['owner'].pk,
            self.memberships['staff'].pk,
            self.memberships['viewer'].pk,
            self.memberships['inactive_staff'].pk,
        ]
        self.assertEqual([m['id'] for m in data['memberships']], expected_ids)
        by_username = {m['username']: m for m in data['memberships']}
        self.assertEqual(by_username['found-owner']['role'], 'owner')
        self.assertTrue(by_username['found-owner']['user_is_active'])
        self.assertEqual(by_username['found-inactive_staff']['role'], 'staff')
        self.assertFalse(by_username['found-inactive_staff']['user_is_active'])

        # Strict exclusion of passwords, password hashes, sessions, saved views, user emails, and foreign dealer
        for forbidden in (
            'SUPER-SECRET-PASSWORD',
            self.users['owner'].password,
            'private-session-key',
            'private-session-payload',
            'PRIVATE-SAVED-VIEW',
            'Foreign foundation dealer',
            'found-foreign',
            'owner-private@example.invalid',
        ):
            self.assertNotIn(forbidden, serialized)
        for member_row in data['memberships']:
            self.assertEqual(
                set(member_row.keys()),
                {'id', 'dealership_id', 'role', 'user_id', 'username', 'user_is_active'},
            )

    def test_owner_only_and_dealership_scope_and_inactive_owner_denied(self):
        for actor in (
            self.users['staff'],
            self.users['viewer'],
            self.users['inactive_staff'],
            self.users['foreign'],
            AnonymousUser(),
        ):
            with self.subTest(actor=str(actor)), self.assertRaises(PermissionDenied):
                self.export(actor=actor)
        with self.assertRaises(PermissionDenied):
            self.export(dealer=self.other)
        self.users['owner'].is_active = False
        self.users['owner'].save(update_fields=['is_active'])
        with self.assertRaises(PermissionDenied):
            self.export()

    def test_synthetic_development_gate(self):
        with override_settings(DEBUG=False), self.assertRaises(PermissionDenied):
            self.export()

    def test_excess_records_or_bytes_fail_closed_without_partial_result(self):
        for limit in ('MAX_MEMBERSHIPS', 'MAX_JSON_BYTES'):
            with self.subTest(limit=limit), patch('core.export.' + limit, 0), self.assertRaises(FoundationExportTooLarge):
                self.export()

    def test_prior_dealership_export_audit_is_scoped_and_bounded(self):
        local = DealershipExportEvent.objects.create(dealership=self.dealer, actor=self.users['owner'],
            format_version='synthetic-v1', sha256='a' * 64, byte_size=1234)
        DealershipExportEvent.objects.create(dealership=self.other, actor=self.users['foreign'],
            format_version='foreign-private', sha256='b' * 64, byte_size=987)
        data = self.export()
        self.assertEqual(data['dealership_export_events'], [{
            'id': local.pk, 'dealership_id': self.dealer.pk, 'actor_id': self.users['owner'].pk,
            'created_at': local.created_at.isoformat(), 'format_version': 'synthetic-v1',
            'sha256': 'a' * 64, 'byte_size': 1234,
        }])
        self.assertNotIn('foreign-private', json.dumps(data))
        self.assertIn('current package event', data['scope'])
        with self.assertRaises(PermissionDenied):
            self.export(actor=self.users['staff'])
        with patch('core.export.MAX_EXPORT_EVENTS', 0), self.assertRaises(FoundationExportTooLarge):
            self.export()

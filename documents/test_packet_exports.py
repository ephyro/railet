# SPDX-License-Identifier: MPL-2.0
import hashlib
import io
import json
import uuid
import zipfile
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import Dealership, Membership
from customers.models import Customer
from inventory.models import Vehicle
from deals.models import DraftDeal
from .models import DemoDealPacket, DemoPacketExportEvent
from .packets import digest, source_digest
from .packet_exports import build_bundle, PacketExportError


@override_settings(DEMO_PACKETS_ENABLED=True)
class PacketExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer=Dealership.objects.create(name='Synthetic export dealer')
        cls.other=Dealership.objects.create(name='Other dealer')
        cls.users={}
        for name,role,dealer in [('owner','owner',cls.dealer),('viewer','viewer',cls.dealer),('foreign','owner',cls.other)]:
            user=get_user_model().objects.create_user(name);cls.users[name]=user
            Membership.objects.create(user=user,role=role,dealership=dealer)
        vehicle=Vehicle.objects.create(dealership=cls.dealer,stock_number='SYN-EXPORT',year=2020,make='Synthetic',model='Sedan')
        buyer=Customer.objects.create(dealership=cls.dealer,first_name='Riley',last_name='Demo')
        cls.deal=DraftDeal.objects.create(dealership=cls.dealer,vehicle=vehicle,buyer=buyer)
        snapshot={'schema_version':1,'deal_id':cls.deal.pk,'worksheet':{'sale_price':'10000.25'},'buyer':{'name':'Riley Demo'}}
        html='<!doctype html><html lang="en"><body>DEMONSTRATION ONLY — Synthetic summary</body></html>'
        cls.packet=DemoDealPacket.objects.create(deal=cls.deal,created_by=cls.users['owner'],created_at=timezone.now(),creation_key=uuid.uuid4(),template_version='demo-summary-v1',snapshot=snapshot,source_sha256=source_digest(snapshot),html=html,artifact_sha256=digest(html))

    def setUp(self):
        self.client.force_login(self.users['owner'])
        self.url=reverse('demo_packet_export',args=[self.deal.pk,self.packet.pk])

    def test_bundle_contains_exact_retained_bytes_snapshot_and_matching_manifest(self):
        response=self.client.get(self.url)
        self.assertEqual(response.status_code,200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(set(archive.namelist()),{'DEMO-summary.html','snapshot.json','README.txt','manifest.json'})
            self.assertEqual(archive.read('DEMO-summary.html'),self.packet.html.encode())
            captured=json.loads(archive.read('snapshot.json'))
            self.assertEqual(captured['snapshot'],self.packet.snapshot)
            self.assertEqual(captured['template_version'],'demo-summary-v1')
            manifest=json.loads(archive.read('manifest.json'))
            for name,expected in manifest['files'].items():
                data=archive.read(name)
                self.assertEqual(len(data),expected['bytes'])
                self.assertEqual(hashlib.sha256(data).hexdigest(),expected['sha256'])
            self.assertTrue(manifest['demonstration_only'])
        event=DemoPacketExportEvent.objects.get()
        self.assertEqual(event.actor,self.users['owner'])
        self.assertEqual(event.bundle_sha256,hashlib.sha256(response.content).hexdigest())
        self.assertIn('attachment;',response['Content-Disposition'])
        self.assertEqual(response['X-Content-Type-Options'],'nosniff')
        self.assertIn('private',response['Cache-Control'])
        self.assertIn('no-store',response['Cache-Control'])

    def test_repeated_exports_are_identical_and_source_changes_do_not_affect_them(self):
        first=self.client.get(self.url).content
        self.deal.archived_at=timezone.now();self.deal.notes='Changed later';self.deal.save()
        second=self.client.get(self.url).content
        self.assertEqual(first,second)
        self.assertEqual(DemoPacketExportEvent.objects.count(),2)

    def test_authorization_precedes_bundle_preparation(self):
        self.client.force_login(self.users['foreign'])
        with patch('documents.packet_exports.build_bundle',side_effect=AssertionError('Do not prepare unauthorized exports')):
            self.assertEqual(self.client.get(self.url).status_code,404)
        self.assertEqual(DemoPacketExportEvent.objects.count(),0)
        self.client.logout();self.assertEqual(self.client.get(self.url).status_code,302)

    def test_viewer_can_export_existing_readable_packet(self):
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.assertEqual(DemoPacketExportEvent.objects.get().actor,self.users['viewer'])
        self.deal.refresh_from_db();self.assertEqual(self.deal.revision,1)

    def test_integrity_failures_do_not_create_audit_or_export(self):
        DemoDealPacket.objects.filter(pk=self.packet.pk).update(html='tampered')
        self.assertEqual(self.client.get(self.url).status_code,409)
        DemoDealPacket.objects.filter(pk=self.packet.pk).update(html=self.packet.html,snapshot={'modified':'synthetic'})
        self.assertEqual(self.client.get(self.url).status_code,409)
        self.assertEqual(DemoPacketExportEvent.objects.count(),0)

    def test_head_has_headers_and_no_body_or_audit_and_post_is_rejected(self):
        response=self.client.head(self.url)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content,b'')
        self.assertGreater(int(response['Content-Length']),0)
        self.assertEqual(DemoPacketExportEvent.objects.count(),0)
        self.assertEqual(self.client.post(self.url).status_code,405)

    @override_settings(DEMO_PACKETS_ENABLED=False)
    def test_gate_closed_before_auth(self):
        self.client.logout()
        response=self.client.get(self.url)
        self.assertEqual(response.status_code,404)
        self.assertIn('no-store',response['Cache-Control'])

    def test_audit_failure_fails_closed_without_releasing_bundle(self):
        with patch('documents.packet_exports.DemoPacketExportEvent.objects.create',side_effect=RuntimeError('synthetic audit failure')):
            with self.assertRaises(RuntimeError):self.client.get(self.url)
        self.assertEqual(DemoPacketExportEvent.objects.count(),0)

    def test_fixed_filenames_and_bounded_payload(self):
        with patch('documents.packet_exports.MAX_PART_BYTES',1):
            with self.assertRaises(PacketExportError):build_bundle(self.packet)
        self.assertEqual(DemoPacketExportEvent.objects.count(),0)

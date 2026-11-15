# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from core.models import Dealership, Membership
from customers.models import Customer
from deals.models import DraftDeal, DraftFinanceProposal, DraftTradeIn
from inventory.models import Vehicle
from .models import DemoDealPacket


@override_settings(DEMO_PACKETS_ENABLED=True)
class DemoPacketTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealership.objects.create(name='Synthetic packet dealer')
        cls.other = Dealership.objects.create(name='Other synthetic dealer')
        cls.users = {}
        for name, role, dealer in [('staff','staff',cls.dealer),('viewer','viewer',cls.dealer),('foreign','owner',cls.other)]:
            user = get_user_model().objects.create_user(name)
            Membership.objects.create(user=user, role=role, dealership=dealer)
            cls.users[name] = user
        cls.vehicle = Vehicle.objects.create(dealership=cls.dealer, stock_number='DEMO-PACKET',year=2020,make='Synthetic',model='Sedan')
        cls.buyer = Customer.objects.create(dealership=cls.dealer,first_name='Synthetic',last_name='Buyer')
        cls.deal = DraftDeal.objects.create(dealership=cls.dealer,vehicle=cls.vehicle,buyer=cls.buyer,sale_price=Decimal('12000.25'),tax=Decimal('700.00'),dealer_fee=Decimal('100.00'),down_payment=Decimal('1000.25'))

    def setUp(self):
        self.client.force_login(self.users['staff'])
        self.url = reverse('demo_packet_list',args=[self.deal.pk])

    def token(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code,200)
        return response.context['token']

    def save(self, token=None):
        return self.client.post(self.url,{'preview_token':token or self.token()})

    def test_preview_does_not_save_and_marks_unknown_facts(self):
        response = self.client.get(self.url)
        self.assertEqual(DemoDealPacket.objects.count(),0)
        snapshot = response.context['snapshot']
        self.assertEqual(snapshot['worksheet_rows'][-1][1],'$11,800.00')
        self.assertTrue(snapshot['reminders'])
        self.assertEqual(snapshot['vehicle']['facts']['Odometer reading'],'Not recorded')
        self.assertIn('private',response['Cache-Control'])

    def test_saved_bytes_and_facts_survive_source_and_template_changes(self):
        response = self.save()
        self.assertEqual(response.status_code,302)
        packet = DemoDealPacket.objects.get()
        original = packet.html
        self.assertIn('DEMONSTRATION ONLY',original)
        self.assertIn('$11,800.00',original)
        self.vehicle.title_brand='rebuilt';self.vehicle.make='Changed';self.vehicle.save()
        self.buyer.first_name='Changed';self.buyer.save()
        self.deal.sale_price=Decimal('20000.00');self.deal.save()
        with patch('documents.packets.render_to_string',side_effect=AssertionError('Must not regenerate saved artifact')):
            artifact = self.client.get(reverse('demo_packet_artifact',args=[self.deal.pk,packet.pk]))
        self.assertEqual(artifact.content.decode(),original)
        packet.refresh_from_db()
        self.assertEqual(packet.snapshot['buyer']['name'],'Synthetic Buyer')
        self.assertEqual(packet.snapshot['vehicle']['facts']['Make'],'Synthetic')
        self.assertEqual(packet.snapshot['worksheet']['sale_price'],'12000.25')
        self.assertIn('sandbox',artifact['Content-Security-Policy'])
        self.assertIn('no-store',artifact['Cache-Control'])

    def test_retry_returns_original_even_after_source_changes(self):
        token=self.token();first=self.save(token)
        self.buyer.email='changed@example.invalid';self.buyer.save()
        second=self.save(token)
        self.assertEqual(first.url,second.url)
        self.assertEqual(DemoDealPacket.objects.count(),1)

    def test_source_changes_require_new_preview(self):
        token=self.token()
        self.vehicle.title_brand='rebuilt';self.vehicle.save()
        response=self.save(token)
        self.assertEqual(response.status_code,409)
        self.assertEqual(DemoDealPacket.objects.count(),0)
        self.assertContains(response,'fresh preview',status_code=409)

    def test_expired_tampered_and_cross_actor_tokens_fail(self):
        token=self.token()
        self.assertEqual(self.save(token+'bad').status_code,400)
        with patch('django.core.signing.time.time',return_value=10): old=self.token()
        self.assertEqual(self.save(old).status_code,400)
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.save(token).status_code,403)
        self.assertEqual(DemoDealPacket.objects.count(),0)

    def test_cross_dealer_and_corrupt_references_fail_closed(self):
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.client.force_login(self.users['staff'])
        foreign = Customer.objects.create(dealership=self.other,first_name='Private',last_name='Synthetic')
        DraftDeal.objects.filter(pk=self.deal.pk).update(buyer=foreign)
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.assertEqual(DemoDealPacket.objects.count(),0)

    def test_viewer_reads_but_cannot_create_and_foreign_cannot_read_artifact(self):
        self.save();packet=DemoDealPacket.objects.get()
        for name,status in [('viewer',200),('foreign',404)]:
            self.client.force_login(self.users[name])
            for route in ('demo_packet_detail','demo_packet_artifact'):
                self.assertEqual(self.client.get(reverse(route,args=[self.deal.pk,packet.pk])).status_code,status)
        self.client.force_login(self.users['viewer'])
        self.assertNotContains(self.client.get(self.url),'Save demo packet')

    @override_settings(DEMO_PACKETS_ENABLED=False)
    def test_gate_closed_even_before_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.assertEqual(self.client.post(self.url).status_code,404)

    def test_html_is_escaped_and_artifact_corruption_is_detected(self):
        self.buyer.first_name='<script>synthetic</script>';self.buyer.save()
        self.save();packet=DemoDealPacket.objects.get()
        self.assertIn('&lt;script&gt;',packet.html)
        self.assertNotIn('<script>synthetic',packet.html)
        DemoDealPacket.objects.filter(pk=packet.pk).update(html='altered')
        self.assertEqual(self.client.get(reverse('demo_packet_artifact',args=[self.deal.pk,packet.pk])).status_code,409)

    def test_zero_rate_and_reading_are_distinct_from_unknown(self):
        self.vehicle.odometer_reading=0;self.vehicle.save()
        self.deal.deal_type='bhph';self.deal.save()
        DraftFinanceProposal.objects.create(deal=self.deal,kind='bhph',annual_contract_rate=Decimal('0'))
        snapshot=self.client.get(self.url).context['snapshot']
        self.assertEqual(snapshot['vehicle']['facts']['Odometer reading'],'0')
        self.assertEqual(snapshot['proposal']['Annual contract rate entered (not APR)'],'0.0000%')

    def test_generation_failure_rolls_back_and_does_not_change_deal_or_events(self):
        token=self.token()
        with patch('documents.packets.render_to_string',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):self.save(token)
        self.assertEqual(DemoDealPacket.objects.count(),0)
        self.save(token)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.revision,1)
        self.assertEqual(self.deal.sale_price,Decimal('12000.25'))
        self.assertEqual(self.deal.events.count(),0)

    def test_method_and_csrf_controls(self):
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.users['staff'])
        self.assertEqual(strict.post(self.url,{'preview_token':self.token()}).status_code,403)
        self.save();packet=DemoDealPacket.objects.get()
        self.assertEqual(self.client.post(reverse('demo_packet_artifact',args=[self.deal.pk,packet.pk])).status_code,405)
        self.assertEqual(self.client.head(reverse('demo_packet_artifact',args=[self.deal.pk,packet.pk])).content,b'')

    def test_proposed_method_is_frozen_in_saved_packet(self):
        self.deal.deal_type='bhph';self.deal.save()
        proposal=DraftFinanceProposal.objects.create(deal=self.deal,kind='bhph',interest_method='precomputed')
        self.assertEqual(self.save().status_code,302)
        packet=DemoDealPacket.objects.get()
        self.assertEqual(packet.snapshot['proposal']['Proposed interest method'],'Precomputed')
        proposal.interest_method='simple';proposal.save()
        packet.refresh_from_db()
        self.assertEqual(packet.snapshot['proposal']['Proposed interest method'],'Precomputed')
        artifact=self.client.get(reverse('demo_packet_artifact',args=[self.deal.pk,packet.pk]))
        self.assertContains(artifact,'Precomputed')

    def test_buyer_and_co_buyer_addresses_are_frozen_in_new_packet(self):
        self.buyer.address_line1='123 Synthetic Lane';self.buyer.city='Demo City';self.buyer.save()
        co=Customer.objects.create(dealership=self.dealer,first_name='Casey',last_name='Demo',address_line1='456 Other Synthetic Lane')
        self.deal.co_buyer=co;self.deal.save()
        self.assertContains(self.client.get(self.url),'123 Synthetic Lane')
        self.assertContains(self.client.get(self.url),'456 Other Synthetic Lane')
        self.assertEqual(self.save().status_code,302)
        packet=DemoDealPacket.objects.get()
        self.assertEqual(packet.template_version,'demo-summary-v6')
        self.assertEqual(packet.snapshot['schema_version'],5)
        self.assertEqual(packet.snapshot['buyer']['address']['city'],'Demo City')
        self.assertEqual(packet.snapshot['co_buyer']['address']['address_line1'],'456 Other Synthetic Lane')
        self.buyer.address_line1='Changed later';self.buyer.save();co.address_line1='Also changed';co.save()
        artifact=self.client.get(reverse('demo_packet_artifact',args=[self.deal.pk,packet.pk]))
        self.assertContains(artifact,'123 Synthetic Lane')
        self.assertContains(artifact,'456 Other Synthetic Lane')
        self.assertNotContains(artifact,'Changed later')

    def test_address_edit_after_preview_requires_a_new_packet_preview(self):
        token=self.token();self.buyer.city='Changed address fact';self.buyer.save()
        self.assertEqual(self.save(token).status_code,409)
        self.assertFalse(DemoDealPacket.objects.exists())

    def test_title_practice_uses_frozen_facts_and_respects_access_and_integrity(self):
        self.vehicle.title_brand = 'rebuilt'
        self.vehicle.save()
        self.save()
        packet = DemoDealPacket.objects.get()
        url = reverse('title_practice', args=[self.deal.pk, packet.pk])
        self.vehicle.title_brand = 'unknown'
        self.vehicle.save()
        response = self.client.get(url)
        self.assertContains(response, 'Rebuilt')
        self.assertContains(response, 'Not a state form')
        self.assertContains(response, 'Not recorded')
        self.assertIn('no-store', response['Cache-Control'])
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.users['staff'])
        DemoDealPacket.objects.filter(pk=packet.pk).update(snapshot={'vehicle': {}})
        self.assertEqual(self.client.get(url).status_code, 409)

    @override_settings(DEMO_PACKETS_ENABLED=False)
    def test_title_practice_disabled_with_demo_gate(self):
        url = reverse('title_practice', args=[self.deal.pk, 1])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_paperwork_review_is_private_and_cannot_report_ready(self):
        self.save()
        packet = DemoDealPacket.objects.get()
        url = reverse('paperwork_review', args=[self.deal.pk, packet.pk])
        response = self.client.get(url)
        self.assertContains(response, 'Practice only')
        self.assertContains(response, 'not a complete list')
        self.assertContains(response, 'Buyers Guide')
        self.assertIn('no-store', response['Cache-Control'])
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.users['staff'])
        DemoDealPacket.objects.filter(pk=packet.pk).update(snapshot={'vehicle': {}})
        self.assertEqual(self.client.get(url).status_code, 409)

    @override_settings(DEMO_PACKETS_ENABLED=False)
    def test_paperwork_review_gate(self):
        self.assertEqual(self.client.get(reverse('paperwork_review', args=[self.deal.pk, 1])).status_code, 404)

    def test_finance_practice_preserves_terms_and_never_implies_disclosure(self):
        self.deal.deal_type = 'bhph'
        self.deal.save()
        proposal = DraftFinanceProposal.objects.create(deal=self.deal, kind='bhph', annual_contract_rate=Decimal('8'))
        self.save()
        packet = DemoDealPacket.objects.get()
        proposal.annual_contract_rate = Decimal('9')
        proposal.save()
        url = reverse('finance_practice', args=[self.deal.pk, packet.pk])
        response = self.client.get(url)
        self.assertContains(response, '8.0000%')
        self.assertNotContains(response, '9.0000%')
        self.assertContains(response, 'not an amount financed or APR')
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.users['staff'])
        DemoDealPacket.objects.filter(pk=packet.pk).update(snapshot={})
        self.assertEqual(self.client.get(url).status_code, 409)

    @override_settings(DEMO_PACKETS_ENABLED=False)
    def test_finance_practice_gate(self):
        self.assertEqual(self.client.get(reverse('finance_practice', args=[self.deal.pk, 1])).status_code, 404)

    def test_paperwork_inventory_tracks_saved_deal_type_and_missing_facts(self):
        self.deal.deal_type = 'bhph'
        self.deal.save()
        self.save()
        packet = DemoDealPacket.objects.get()
        self.deal.deal_type = 'cash'
        self.deal.save()
        response = self.client.get(reverse('paperwork_review', args=[self.deal.pk, packet.pk]))
        self.assertContains(response, 'Retail installment contract and credit disclosures')
        self.assertContains(response, 'Title brand verification')
        self.assertContains(response, 'VIN')
        self.assertContains(response, 'not a preserved form or approval record')

    def test_packet_freezes_research_inventory_and_preserves_exported_html(self):
        from io import BytesIO
        from zipfile import ZipFile
        from .form_registry import REGISTRY_VERSION
        self.deal.deal_type = 'bhph'
        self.deal.save()
        preview = self.client.get(self.url)
        self.assertContains(preview, REGISTRY_VERSION)
        self.assertContains(preview, 'Retail installment contract and credit disclosures')
        self.save()
        packet = DemoDealPacket.objects.get()
        self.assertIn(REGISTRY_VERSION, packet.html)
        self.assertIn('Retail installment contract and credit disclosures', packet.html)
        self.assertIn('do not determine applicability', packet.html)
        with patch('documents.packets.research_inventory', side_effect=AssertionError('Must not regenerate saved inventory')):
            artifact = self.client.get(reverse('demo_packet_artifact', args=[self.deal.pk, packet.pk]))
            exported = self.client.get(reverse('demo_packet_export', args=[self.deal.pk, packet.pk]))
        self.assertEqual(artifact.content.decode(), packet.html)
        with ZipFile(BytesIO(exported.content)) as archive:
            self.assertEqual(archive.read('DEMO-summary.html'), artifact.content)

    def test_registry_change_requires_new_preview(self):
        token = self.token()
        with patch('documents.packet_views.REGISTRY_VERSION', 'future-research-version'):
            response = self.save(token)
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, 'research inventory changed', status_code=409)
        self.assertFalse(DemoDealPacket.objects.exists())

    def test_registry_update_preserves_old_packet_and_export_bytes(self):
        from dataclasses import replace
        from io import BytesIO
        from zipfile import ZipFile
        from .form_registry import REGISTRY_VERSION, research_inventory

        old_version = 'fl-research-2026-11-07-v2'
        def old_inventory(snapshot):
            entries = research_inventory(snapshot)
            for entry in entries:
                if entry['reference'].key == 'title':
                    entry['reference'] = replace(entry['reference'], revision='07/23 on referenced form; verify current')
            return entries

        with patch('documents.packet_views.REGISTRY_VERSION', old_version), \
             patch('documents.packets.REGISTRY_VERSION', old_version), \
             patch('documents.packets.research_inventory', side_effect=old_inventory):
            old_token = self.token()
            self.assertEqual(self.save(old_token).status_code, 302)
            stale_token = self.token()
        old_packet = DemoDealPacket.objects.get()
        old_html = old_packet.html.encode('utf-8')
        self.assertIn(old_version.encode(), old_html)
        self.assertIn(b'07/23 on referenced form; verify current', old_html)
        self.assertEqual(self.save(stale_token).status_code, 409)
        self.assertEqual(self.save().status_code, 302)
        new_packet = DemoDealPacket.objects.exclude(pk=old_packet.pk).get()
        self.assertIn(REGISTRY_VERSION, new_packet.html)
        self.assertIn('direct PDF unavailable at review', new_packet.html)
        old_packet.refresh_from_db()
        self.assertEqual(old_packet.html.encode('utf-8'), old_html)
        artifact = self.client.get(reverse('demo_packet_artifact', args=[self.deal.pk, old_packet.pk]))
        exported = self.client.get(reverse('demo_packet_export', args=[self.deal.pk, old_packet.pk]))
        self.assertEqual(artifact.content, old_html)
        with ZipFile(BytesIO(exported.content)) as archive:
            self.assertEqual(archive.read('DEMO-summary.html'), old_html)

    def test_odometer_research_revision_preserves_v3_artifact_and_requires_fresh_preview(self):
        from dataclasses import replace
        from io import BytesIO
        from zipfile import ZipFile
        from .form_registry import REGISTRY_VERSION, research_inventory

        old_version = 'fl-research-2026-11-07-v3'
        def old_inventory(snapshot):
            entries = [entry for entry in research_inventory(snapshot)
                       if entry['reference'].key not in ('dealer-reassignment', 'secure-odometer-poa')]
            for entry in entries:
                if entry['reference'].key == 'odometer':
                    entry['reference'] = replace(entry['reference'], name='Legacy odometer research topic',
                        revision='Depends on document; verify current')
            return entries

        with patch('documents.packet_views.REGISTRY_VERSION', old_version), \
             patch('documents.packets.REGISTRY_VERSION', old_version), \
             patch('documents.packets.research_inventory', side_effect=old_inventory):
            self.assertEqual(self.save(self.token()).status_code, 302)
            stale = self.token()
        old_packet = DemoDealPacket.objects.get()
        original_html = old_packet.html.encode('utf-8')
        original_snapshot = old_packet.snapshot
        self.assertIn(b'Legacy odometer research topic', original_html)
        self.assertEqual(self.save(stale).status_code, 409)
        self.assertEqual(self.save().status_code, 302)
        new_packet = DemoDealPacket.objects.exclude(pk=old_packet.pk).get()
        self.assertIn(REGISTRY_VERSION, new_packet.html)
        self.assertIn('Secure odometer power of attorney', new_packet.html)
        self.assertIn('Dealer title reassignment supplement', new_packet.html)
        old_packet.refresh_from_db()
        self.assertEqual(old_packet.html.encode('utf-8'), original_html)
        self.assertEqual(old_packet.snapshot, original_snapshot)
        artifact = self.client.get(reverse('demo_packet_artifact', args=[self.deal.pk, old_packet.pk]))
        exported = self.client.get(reverse('demo_packet_export', args=[self.deal.pk, old_packet.pk]))
        self.assertEqual(artifact.content, original_html)
        with ZipFile(BytesIO(exported.content)) as archive:
            self.assertEqual(archive.read('DEMO-summary.html'), original_html)

    def test_provenance_correction_preserves_v4_packet_and_invalidates_preview(self):
        from dataclasses import replace
        from io import BytesIO
        from zipfile import ZipFile
        from .form_registry import REGISTRY_VERSION, research_inventory

        def v4_inventory(snapshot):
            entries = research_inventory(snapshot)
            for entry in entries:
                if entry['reference'].key == 'secure-odometer-poa':
                    entry['reference'] = replace(entry['reference'],
                        revision='FLHSMV TL-02 marked rev. 03/25, effective immediately; current procedure and secure-form revision unconfirmed.')
            return entries

        with patch('documents.packet_views.REGISTRY_VERSION', 'fl-research-2026-11-10-v4'), \
             patch('documents.packets.REGISTRY_VERSION', 'fl-research-2026-11-10-v4'), \
             patch('documents.packets.research_inventory', side_effect=v4_inventory):
            self.assertEqual(self.save(self.token()).status_code, 302)
            stale = self.token()
        old = DemoDealPacket.objects.get()
        old_html, old_snapshot = old.html.encode(), old.snapshot
        self.assertIn(b'FLHSMV TL-02 marked rev. 03/25', old_html)
        self.assertEqual(self.save(stale).status_code, 409)
        self.assertEqual(self.save().status_code, 302)
        new = DemoDealPacket.objects.exclude(pk=old.pk).get()
        self.assertIn(REGISTRY_VERSION, new.html)
        self.assertIn('direct PDF blocked', new.html)
        old.refresh_from_db()
        self.assertEqual((old.html.encode(), old.snapshot), (old_html, old_snapshot))
        artifact = self.client.get(reverse('demo_packet_artifact', args=[self.deal.pk, old.pk]))
        exported = self.client.get(reverse('demo_packet_export', args=[self.deal.pk, old.pk]))
        self.assertEqual(artifact.content, old_html)
        with ZipFile(BytesIO(exported.content)) as archive:
            self.assertEqual(archive.read('DEMO-summary.html'), old_html)

    def test_credit_research_v6_requires_fresh_preview_and_preserves_v5_packet(self):
        from dataclasses import replace
        from io import BytesIO
        from zipfile import ZipFile
        from .form_registry import REGISTRY_VERSION, research_inventory

        self.deal.deal_type = 'bhph'
        self.deal.save()
        def v5_inventory(snapshot):
            entries = research_inventory(snapshot)
            for entry in entries:
                if entry['reference'].key == 'retail-installment':
                    entry['reference'] = replace(entry['reference'], publisher='Not selected',
                        revision='Not selected', rights='Template rights not established',
                        applicability='Review whether closed-end credit rules and Florida retail installment requirements apply.',
                        review='Obtain reviewed contract; independently verify figures, disclosures, signing and delivery.')
            return entries

        with patch('documents.packet_views.REGISTRY_VERSION', 'fl-research-2026-11-10-v5'), \
             patch('documents.packets.REGISTRY_VERSION', 'fl-research-2026-11-10-v5'), \
             patch('documents.packets.research_inventory', side_effect=v5_inventory):
            self.assertEqual(self.save(self.token()).status_code, 302)
            stale = self.token()
        old = DemoDealPacket.objects.get()
        old_html, old_snapshot, old_hash = old.html.encode(), old.snapshot, old.artifact_sha256
        self.assertIn(b'Obtain reviewed contract; independently verify figures', old_html)
        self.assertEqual(self.save(stale).status_code, 409)
        self.assertEqual(DemoDealPacket.objects.count(), 1)
        self.assertEqual(self.save().status_code, 302)
        new = DemoDealPacket.objects.exclude(pk=old.pk).get()
        self.assertIn(REGISTRY_VERSION, new.html)
        self.assertIn('APR as annual credit cost rate', new.html)
        self.assertIn('total of payments as scheduled payments', new.html)
        old.refresh_from_db()
        self.assertEqual((old.html.encode(), old.snapshot, old.artifact_sha256), (old_html, old_snapshot, old_hash))
        artifact = self.client.get(reverse('demo_packet_artifact', args=[self.deal.pk, old.pk]))
        exported = self.client.get(reverse('demo_packet_export', args=[self.deal.pk, old.pk]))
        self.assertEqual(artifact.content, old_html)
        with ZipFile(BytesIO(exported.content)) as archive:
            self.assertEqual(archive.read('DEMO-summary.html'), old_html)

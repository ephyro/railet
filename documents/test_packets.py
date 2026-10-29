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
        self.assertEqual(packet.template_version,'demo-summary-v5')
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

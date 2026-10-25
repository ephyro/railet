# SPDX-License-Identifier: MPL-2.0
"""Synthetic demonstration summaries. No legal forms or finalization behavior."""
import hashlib
import json
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.template.loader import render_to_string
from django.utils import timezone
from core.models import Dealership, Membership
from customers.models import Customer
from deals.models import DraftDeal, MONEY_FIELDS, FINANCING_TYPES
from deals.review import build_review_reminders, money_text
from deals.worksheet import draft_totals
from inventory.models import Vehicle
from .models import DemoDealPacket

TEMPLATE_VERSION = 'demo-summary-v3'


class PacketChanged(Exception):
    pass


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def source_digest(snapshot):
    return digest(json.dumps(snapshot, sort_keys=True, separators=(',', ':'), ensure_ascii=False))


def check_gate():
    if not getattr(settings, 'DEMO_PACKETS_ENABLED', False):
        raise Http404


def recorded(value):
    return 'Not recorded' if value is None or value == '' else str(value)


def build_snapshot(deal):
    vehicle = deal.vehicle
    trade = deal.trades.filter(archived_at__isnull=True).first()
    proposal = deal.finance_proposals.filter(kind=deal.deal_type).first() if deal.deal_type in FINANCING_TYPES else None
    def person(customer):
        if customer is None:
            return None
        return {'record_id': customer.pk, 'name': str(customer), 'phone': customer.phone, 'email': customer.email}
    def identity(record):
        return {
            'VIN': recorded(record.vin), 'Year': recorded(record.year), 'Make': recorded(record.make), 'Model': recorded(record.model),
            'Title brand as recorded': record.get_title_brand_display(),
            'Odometer reading': recorded(record.odometer_reading),
            'Odometer unit': record.get_odometer_unit_display(), 'Mileage status as recorded': record.get_odometer_status_display(),
        }
    totals = draft_totals({name: getattr(deal, name) for name in MONEY_FIELDS})
    reminders = build_review_reminders(deal, trade, proposal, {name: '#' for name in ('vehicle','buyer','co_buyer','deal','trade','proposal')})
    proposal_data = None
    if proposal:
        proposal_data = {
            'Proposed interest method': proposal.get_interest_method_display(),
            'Creditor or funding source': recorded(proposal.creditor_name),
            'Payment frequency': proposal.get_payment_frequency_display() if proposal.payment_frequency else 'Not recorded',
            'Payment count': recorded(proposal.payment_count),
            'Annual contract rate entered (not APR)': f'{proposal.annual_contract_rate:.4f}%' if proposal.annual_contract_rate is not None else 'Not recorded',
            'First payment date': proposal.first_payment_date.isoformat() if proposal.first_payment_date else 'Not recorded',
        }
    return {
        'schema_version': 3, 'archive_state': 'Archived draft' if deal.archived_at else 'Active draft', 'deal_id': deal.pk, 'deal_revision': deal.revision,
        'dealership': deal.dealership.name, 'deal_type': deal.get_deal_type_display(),
        'vehicle': {'record_id': vehicle.pk, 'stock_number': vehicle.stock_number, 'description': str(vehicle),
                    'facts': identity(vehicle), 'title_received': vehicle.title_received},
        'buyer': person(deal.buyer), 'co_buyer': person(deal.co_buyer),
        'worksheet': {name: str(getattr(deal, name)) for name in MONEY_FIELDS},
        'worksheet_rows': [
            ['Vehicle price', money_text(deal.sale_price)], ['Sales tax entered', money_text(deal.tax)],
            ['Title / registration fees entered', money_text(deal.title_registration)], ['Dealer fee entered', money_text(deal.dealer_fee)],
            ['Trade allowance', money_text(deal.trade_allowance)], ['Estimated trade payoff', money_text(deal.trade_payoff)],
            ['Planned down payment (not money received)', money_text(deal.down_payment)],
            ['Draft estimate balance (not amount financed or payoff)', money_text(totals['balance'])],
        ],
        'trade': {'record_id': trade.pk, 'facts': identity(trade), 'lienholder': trade.lienholder_name,
                  'payoff_good_through': trade.payoff_good_through.isoformat() if trade.payoff_good_through else None} if trade else None,
        'proposal': proposal_data,
        'reminders': [{'title': item['title'], 'detail': item['detail']} for item in reminders],
    }


def locked_source(dealership_id, deal_id):
    """Parent lock coordinates children; explicit related row locks freeze canonical facts."""
    deal = DraftDeal.objects.select_for_update().get(pk=deal_id, dealership_id=dealership_id)
    deal.dealership = Dealership.objects.get(pk=dealership_id)
    vehicle = Vehicle.objects.select_for_update().get(pk=deal.vehicle_id, dealership_id=dealership_id)
    ids = [deal.buyer_id] + ([deal.co_buyer_id] if deal.co_buyer_id else [])
    people = {person.pk: person for person in Customer.objects.select_for_update().filter(pk__in=ids, dealership_id=dealership_id).order_by('pk')}
    if len(people) != len(set(ids)):
        raise Http404
    deal.vehicle = vehicle
    deal.buyer = people[deal.buyer_id]
    deal.co_buyer = people.get(deal.co_buyer_id)
    return deal


def packet_source(*, dealership_id, deal_id):
    check_gate()
    with transaction.atomic():
        Dealership.objects.select_for_update().get(pk=dealership_id)
        try:
            return build_snapshot(locked_source(dealership_id, deal_id))
        except (DraftDeal.DoesNotExist, Vehicle.DoesNotExist) as error:
            raise Http404 from error


def create_packet(*, dealership_id, deal_id, actor, creation_key, expected_source):
    check_gate()
    with transaction.atomic():
        try:
            membership = Membership.objects.select_for_update().get(user=actor, dealership_id=dealership_id)
        except Membership.DoesNotExist as error:
            raise PermissionDenied from error
        if membership.role not in (Membership.Role.OWNER, Membership.Role.STAFF):
            raise PermissionDenied
        Dealership.objects.select_for_update().get(pk=dealership_id)
        prior = DemoDealPacket.objects.filter(deal_id=deal_id, deal__dealership_id=dealership_id, creation_key=creation_key).first()
        if prior:
            if prior.source_sha256 != expected_source or prior.created_by_id != actor.pk:
                raise PacketChanged('This creation key belongs to a different snapshot. Review the saved packet or start again.')
            return prior, False
        try:
            snapshot = build_snapshot(locked_source(dealership_id, deal_id))
        except (DraftDeal.DoesNotExist, Vehicle.DoesNotExist) as error:
            raise Http404 from error
        if source_digest(snapshot) != expected_source:
            raise PacketChanged('The saved deal or a linked record changed after preview. Review a fresh preview before saving.')
        now = timezone.now()
        html = render_to_string('documents/demo_packet_artifact.html', {'snapshot': snapshot, 'captured_at': now, 'template_version': TEMPLATE_VERSION})
        return DemoDealPacket.objects.create(
            deal_id=deal_id, created_by=actor, created_at=now, creation_key=creation_key,
            template_version=TEMPLATE_VERSION, snapshot=snapshot, source_sha256=expected_source,
            html=html, artifact_sha256=digest(html),
        ), True

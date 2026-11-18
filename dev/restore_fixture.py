# SPDX-License-Identifier: MPL-2.0
"""Seed or verify only the disposable cluster created by restore_exercise.py."""
import hashlib
import json
import os
from datetime import timedelta
from decimal import Decimal
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import sys
from uuid import uuid4
import zipfile

root = Path(os.environ.get('RAILET_RESTORE_EXERCISE_ROOT', '/nonexistent')).resolve()
mode = sys.argv[1] if len(sys.argv) == 2 else ''
expected_db = {'seed': 'exercise_source', 'verify': 'exercise_restore'}.get(mode)
expected_media = root / ('source-media' if mode == 'seed' else 'restore-media')
if (not expected_db or root.parent != Path('/tmp') or not root.name.startswith('railet-restore-exercise-')
        or not (root / 'marker').is_file() or os.environ.get('POSTGRES_DB') != expected_db
        or os.environ.get('POSTGRES_HOST') != str(root / 'socket')
        or os.environ.get('RAILET_PRIVATE_MEDIA_ROOT') != str(expected_media)
        or os.environ.get('RAILET_SQLITE') != '0' or os.environ.get('RAILET_DEBUG') != '1'):
    raise SystemExit('Refusing to run outside the isolated synthetic exercise.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'railet.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from django.http import Http404
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from core.models import AuditEvent, Dealership, DealershipExportEvent, Membership
from customers.export import export_customers
from customers.message_simulator import mock_status, record_mock_event, submit_mock
from customers.models import Customer, CustomerActivity, CustomerEvent, MockMessageEvent, MockMessageSubmission
from inventory.models import Vehicle, VehiclePhoto, VehicleVendor, VehicleVendorEvent, ReconTask, VehicleCostEntry
from inventory.photos import add_photos, normalize_photo
from inventory.reconditioning import add_cost, add_task, reverse_cost, save_vendor, with_cost_totals
from deals.account_context import completed_account_snapshot
from deals.completion import (complete, create_follow_on_draft, preview, preview_follow_on_draft,
                              preview_void, verified_snapshot, void_completion)
from deals.models import (DealEvent, DealFollowUp, DemoCompletionVoid, DemoDealCompletion,
                          DemoFollowOnDraft, DraftDeal, DraftFinanceProposal, DraftTradeIn, FollowUpEvent)
from finance.account_services import open_from_draft
from finance.models import DemoAccountContext, DemoBook, DemoPosting, DemoSchedule, DemoServicingPlan
from finance.schedule_services import calculate_for_book, result_digest, save_illustration
from finance.services import open_book, record_receipt, reverse_receipt, reconcile
from finance.servicing_services import projection_for_book, select_baseline
from feedback.export import export_feedback
from feedback.models import FeedbackReport
from documents.models import (DealFile, DealFileEvent, VehicleInvoice,
                              VehicleInvoiceEvent, VehicleAcquisitionFile,
                              VehicleAcquisitionFileEvent)
from documents.invoice_views import upload_invoice
from documents.acquisition_views import upload_acquisition_file
from documents.services import upload_deal_file
from documents.models import DemoDealPacket, DemoPacketExportEvent
from documents.packets import create_packet, packet_source, source_digest, digest
from documents.form_registry import REGISTRY_VERSION

PDF = b'%PDF-1.7\nInvented private restore fixture\n%%EOF\n'
INVOICE_PDF = b'%PDF-1.7\nInvented vehicle invoice restore fixture\n%%EOF\n'
ACQUISITION_PDF = b'%PDF-1.7\nInvented vehicle acquisition restore fixture\n%%EOF\n'


def audit_state():
    rows = list(AuditEvent.objects.order_by('pk').values(
        'id', 'dealership_id', 'vehicle_id', 'actor_id', 'action', 'changes', 'created_at'))
    for row in rows:
        row['created_at'] = row['created_at'].isoformat()
    return rows


def ledger_state():
    # Capture every stored field, including IDs, timestamps, keys and provenance.
    return json.loads(json.dumps({
        'books': list(DemoBook.objects.order_by('pk').values()),
        'postings': list(DemoPosting.objects.order_by('pk').values()),
    }, cls=DjangoJSONEncoder, sort_keys=True))


def servicing_state():
    return json.loads(json.dumps({
        'schedules': list(DemoSchedule.objects.order_by('pk').values()),
        'plans': list(DemoServicingPlan.objects.order_by('pk').values()),
    }, cls=DjangoJSONEncoder, sort_keys=True))


def handoff_state():
    completions = list(DemoDealCompletion.objects.order_by('pk').values())
    packet_ids = [record['packet_id'] for record in completions]
    return json.loads(json.dumps({
        'completions': completions,
        'packets': list(DemoDealPacket.objects.filter(pk__in=packet_ids).order_by('pk').values()),
        'contexts': list(DemoAccountContext.objects.order_by('pk').values()),
    }, cls=DjangoJSONEncoder, sort_keys=True))


def deal_state():
    return json.loads(json.dumps({
        'drafts': list(DraftDeal.objects.order_by('pk').values()),
        'proposals': list(DraftFinanceProposal.objects.order_by('pk').values()),
        'trades': list(DraftTradeIn.objects.order_by('pk').values()),
        'events': list(DealEvent.objects.order_by('pk').values()),
        'follow_ups': list(DealFollowUp.objects.order_by('pk').values()),
        'follow_up_events': list(FollowUpEvent.objects.order_by('pk').values()),
        'voids': list(DemoCompletionVoid.objects.order_by('pk').values()),
        'follow_on_drafts': list(DemoFollowOnDraft.objects.order_by('pk').values()),
    }, cls=DjangoJSONEncoder, sort_keys=True))


def customer_activity_state():
    return json.loads(json.dumps({
        'activities': list(CustomerActivity.objects.order_by('pk').values()),
        'customer_events': list(CustomerEvent.objects.order_by('pk').values()),
        'mock_submissions': list(MockMessageSubmission.objects.order_by('pk').values()),
        'mock_events': list(MockMessageEvent.objects.order_by('pk').values()),
    }, cls=DjangoJSONEncoder, sort_keys=True))


def reconditioning_state():
    return json.loads(json.dumps({
        'vendors': list(VehicleVendor.objects.order_by('pk').values()),
        'vendor_events': list(VehicleVendorEvent.objects.order_by('pk').values()),
        'tasks': list(ReconTask.objects.order_by('pk').values()),
        'costs': list(VehicleCostEntry.objects.order_by('pk').values()),
    }, cls=DjangoJSONEncoder, sort_keys=True))


def invoice_event_state():
    return json.loads(json.dumps(list(VehicleInvoiceEvent.objects.order_by('pk').values()),
                                 cls=DjangoJSONEncoder, sort_keys=True))


def deal_file_event_state():
    return json.loads(json.dumps(list(DealFileEvent.objects.order_by('pk').values()),
                                 cls=DjangoJSONEncoder, sort_keys=True))


def packet_export_event_state():
    return json.loads(json.dumps(list(DemoPacketExportEvent.objects.order_by('pk').values()),
                                 cls=DjangoJSONEncoder, sort_keys=True))


def feedback_state():
    return json.loads(json.dumps({
        'reports': list(FeedbackReport.objects.order_by('pk').values()),
        'package_events': list(DealershipExportEvent.objects.order_by('pk').values()),
    }, cls=DjangoJSONEncoder, sort_keys=True))


def hidden_input(response, name):
    class Inputs(HTMLParser):
        def __init__(self):
            super().__init__()
            self.values = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'input' and attrs.get('name') == name:
                self.values.append(attrs.get('value'))

    inputs = Inputs()
    inputs.feed(response.content.decode('utf-8'))
    assert len(inputs.values) == 1 and inputs.values[0]
    return inputs.values[0]


def assert_guard_rejects(label, operation):
    try:
        with transaction.atomic():
            operation()
    except DatabaseError as error:
        if label not in str(error) or getattr(error.__cause__, 'sqlstate', None) != 'P0001':
            raise AssertionError('Unexpected database failure while verifying a guard') from error
    else:
        raise AssertionError(f'Expected audit guard did not reject: {label}')


def seed():
    dealer = Dealership.objects.create(name='Synthetic restore dealer')
    foreign_dealer = Dealership.objects.create(name='Synthetic foreign dealer')
    owner = get_user_model().objects.create_user('restore-exercise-owner')
    staff = get_user_model().objects.create_user('restore-exercise-staff')
    viewer = get_user_model().objects.create_user('restore-exercise-viewer')
    foreign = get_user_model().objects.create_user('restore-exercise-foreign')
    Membership.objects.create(user=owner, dealership=dealer, role='owner')
    Membership.objects.create(user=staff, dealership=dealer, role='staff')
    Membership.objects.create(user=viewer, dealership=dealer, role='viewer')
    Membership.objects.create(user=foreign, dealership=foreign_dealer, role='owner')
    buyer = Customer.objects.create(dealership=dealer, first_name='Synthetic', last_name='Restore')
    activity_client = Client()
    activity_client.force_login(owner)
    activity_response = activity_client.post(reverse('customer_activity_create', args=[buyer.pk]), {
        'kind': 'follow_up', 'detail': 'Synthetic restore follow-up',
        'assigned_to': staff.pk, 'creation_key': str(uuid4()),
    })
    assert activity_response.status_code == 302
    activity = CustomerActivity.objects.get(customer=buyer)
    assert activity_client.post(reverse('customer_activity_complete', args=[buyer.pk, activity.pk]),
        {'revision': activity.revision}).status_code == 302
    with override_settings(DEMO_MESSAGE_SIMULATOR_ENABLED=True):
        submission, created = submit_mock(dealership_id=dealer.pk, actor=staff, submission_id=uuid4(),
            recipient_label='mock-recipient-alpha', scenario='mock-follow-up')
        assert created
        for label in ('mock-accepted', 'mock-delivered'):
            _, created = record_mock_event(dealership_id=dealer.pk, actor=staff, submission_id=submission.submission_id,
                event_id=uuid4(), label=label)
            assert created
        assert mock_status(dealership_id=dealer.pk, actor=owner, submission_id=submission.submission_id) == 'mock-delivered'
    (root / 'customer-activity-baseline.json').write_text(json.dumps(customer_activity_state(), sort_keys=True))
    vehicle = Vehicle.objects.create(dealership=dealer, stock_number='RESTORE-SYNTHETIC', year=2020, make='Synthetic', model='Sedan')
    AuditEvent.objects.create(dealership=dealer, vehicle=vehicle, actor=owner, action='created',
                              changes={'stock_number': {'before': None, 'after': 'RESTORE-SYNTHETIC'}})
    image_bytes = BytesIO()
    with Image.new('RGB', (40, 20), color=(25, 90, 65)) as image:
        image.save(image_bytes, format='PNG')
    upload = SimpleUploadedFile('synthetic.png', image_bytes.getvalue(), content_type='image/png')
    original, thumbnail = normalize_photo(upload)
    photo = add_photos(vehicle, [(original, thumbnail)], actor=owner)[0]
    (root / 'expected-photo.jpg').write_bytes(original)
    (root / 'expected-thumbnail.jpg').write_bytes(thumbnail)
    invoice = upload_invoice(vehicle_id=vehicle.pk, dealership_id=dealer.pk, actor=owner,
        title='Synthetic vehicle invoice', upload_key=uuid4(), pdf_bytes=INVOICE_PDF, cost_id=None)
    acquisition, acquisition_created = upload_acquisition_file(vehicle_id=vehicle.pk,
        dealership_id=dealer.pk, actor=owner, title='Synthetic acquisition PDF',
        description='Unverified synthetic document', upload_key=uuid4(), pdf_bytes=ACQUISITION_PDF)
    assert acquisition_created and photo.vehicle_id == vehicle.pk
    assert invoice.sha256 == hashlib.sha256(INVOICE_PDF).hexdigest()
    assert acquisition.sha256 == hashlib.sha256(ACQUISITION_PDF).hexdigest()
    deal = DraftDeal.objects.create(dealership=dealer, buyer=buyer, vehicle=vehicle)
    snapshot = packet_source(dealership_id=dealer.pk, deal_id=deal.pk)
    packet, created = create_packet(dealership_id=dealer.pk, deal_id=deal.pk, actor=owner,
        creation_key=uuid4(), expected_source=source_digest(snapshot))
    assert created and packet.snapshot == snapshot
    packet_export_client = Client()
    packet_export_client.force_login(owner)
    packet_export_response = packet_export_client.get(reverse('demo_packet_export', args=[deal.pk, packet.pk]))
    assert packet_export_response.status_code == 200
    packet_export_event = DemoPacketExportEvent.objects.get(packet=packet)
    assert packet_export_event.actor_id == owner.pk
    assert packet_export_event.bundle_sha256 == hashlib.sha256(packet_export_response.content).hexdigest()
    (root / 'packet-export-event-baseline.json').write_text(json.dumps(packet_export_event_state(), sort_keys=True))
    packet_baseline = list(DemoDealPacket.objects.filter(pk=packet.pk).values())
    (root / 'packet-baseline.json').write_text(json.dumps(packet_baseline, cls=DjangoJSONEncoder, sort_keys=True))
    attachment, created = upload_deal_file(deal_id=deal.pk, dealership_id=dealer.pk, actor=owner,
        title='Synthetic private file', upload_key=uuid4(), pdf_bytes=PDF)
    assert created and attachment.sha256 == hashlib.sha256(PDF).hexdigest()
    assert DealFileEvent.objects.filter(file=attachment, action='upload').count() == 1
    today = timezone.localdate()
    book, created = open_book(dealership_id=dealer.pk, customer_id=buyer.pk, actor=owner,
        label='Synthetic restore account', source_reference='Invented restore opening',
        opening_on=today, opening_amount='10000.25', request_key=uuid4())
    receipt, receipt_created = record_receipt(dealership_id=dealer.pk, book_id=book.pk,
        actor=owner, amount='125.50', effective_on=today, reason='Invented restore receipt',
        payment_method=DemoPosting.PaymentMethod.CASH, request_key=uuid4())
    reversal, reversal_created = reverse_receipt(dealership_id=dealer.pk, book_id=book.pk,
        posting_id=receipt.pk, actor=owner, effective_on=today,
        reason='Invented restore correction', request_key=uuid4())
    assert created and receipt_created and reversal_created and reversal.reverses_id == receipt.pk
    inputs = {'method': 'precomputed', 'first_due_on': (today + timedelta(days=1)).isoformat(),
              'count': 3, 'frequency': 'monthly', 'first_day': None, 'second_day': None,
              'finance_charge': '199.75', 'contract_rate': None, 'regular_payment': None}
    expected_digest = result_digest(calculate_for_book(book, inputs))
    schedule, schedule_created = save_illustration(dealership_id=dealer.pk, book_id=book.pk,
        actor=owner, inputs=inputs, expected_digest=expected_digest, creation_key=uuid4())
    plan, plan_created = select_baseline(dealership_id=dealer.pk, book_id=book.pk,
        schedule_id=schedule.pk, actor=owner, reason='Invented restore baseline',
        creation_key=uuid4(), expected_digest=expected_digest)
    assert schedule_created and plan_created and plan.schedule_id == schedule.pk
    completed_deal = DraftDeal.objects.create(dealership=dealer, buyer=buyer, vehicle=vehicle,
        deal_type='bhph', sale_price=Decimal('10000.25'))
    DraftFinanceProposal.objects.create(deal=completed_deal, kind='bhph', interest_method='precomputed',
        creditor_name='Synthetic creditor', payment_frequency='monthly', payment_count=3,
        first_payment_date=today + timedelta(days=30), illustration_finance_charge=Decimal('199.75'))
    trade_client = Client()
    trade_client.force_login(owner)
    trade_response = trade_client.post(reverse('trade_edit', args=[completed_deal.pk]), {
        'revision': completed_deal.revision, 'vin': 'SYNTHETIC-RESTORE-TRADE',
        'year': '2012', 'make': 'Synthetic', 'model': 'Trade', 'title_brand': 'rebuilt',
        'odometer_reading': '123456', 'odometer_unit': 'miles', 'odometer_status': 'not_actual',
        'lienholder_name': 'Synthetic payoff recipient', 'trade_allowance': '1500.00',
        'trade_payoff': '250.00', 'notes': 'Invented trade record',
    })
    assert trade_response.status_code == 302
    completed_deal.refresh_from_db()
    review = preview(dealership_id=dealer.pk, deal_id=completed_deal.pk)
    assert not review['blockers']
    completion = complete(dealership_id=dealer.pk, deal_id=completed_deal.pk, actor=owner,
        creation_key=uuid4(), expected_review=review['review_sha256'],
        review_notes='Invented handoff; recorded reminders require review.', reviewed=True, demo_confirmed=True)
    context_snapshot = completed_account_snapshot(completed_deal)
    handoff_book, handoff_created = open_from_draft(dealership_id=dealer.pk, deal_id=completed_deal.pk,
        actor=owner, opening_amount='10000.25', opening_on=today, source_reference='Invented handoff opening',
        request_key=uuid4(), expected_digest=result_digest(context_snapshot))
    assert handoff_created and DemoAccountContext.objects.get(book=handoff_book).snapshot['completion_id'] == completion.pk
    void_source = DraftDeal.objects.create(dealership=dealer, buyer=buyer, vehicle=vehicle,
        deal_type='cash', sale_price=Decimal('3500.00'))
    void_source_review = preview(dealership_id=dealer.pk, deal_id=void_source.pk)
    assert not void_source_review['blockers']
    void_source_completion = complete(dealership_id=dealer.pk, deal_id=void_source.pk, actor=owner,
        creation_key=uuid4(), expected_review=void_source_review['review_sha256'],
        review_notes='Invented void source and reminders.', reviewed=True, demo_confirmed=True)
    _, void_digest, prior = preview_void(dealership_id=dealer.pk, deal_id=void_source.pk, actor=owner)
    assert prior is None
    void = void_completion(dealership_id=dealer.pk, deal_id=void_source.pk, actor=owner,
        creation_key=uuid4(), expected_review=void_digest, reason='Invented void rehearsal')
    follow_on_preview = preview_follow_on_draft(dealership_id=dealer.pk, deal_id=void_source.pk, actor=owner)
    assert follow_on_preview['money_copied'] and follow_on_preview['amounts']['sale_price'] == Decimal('3500.00')
    follow_on = create_follow_on_draft(dealership_id=dealer.pk, deal_id=void_source.pk, actor=owner,
        creation_key=uuid4(), expected_review=follow_on_preview['review_sha256'],
        reason='Invented follow-on rehearsal', confirmed=True)
    assert void.completion_id == void_source_completion.pk and follow_on.void_rehearsal_id == void.pk
    follow_client = Client()
    follow_client.force_login(owner)
    follow_data = {'title': 'Synthetic deal follow-up', 'detail': 'Invented internal reminder',
                   'assigned_to': staff.pk, 'due_on': today.isoformat(), 'revision': 1,
                   'creation_key': str(uuid4())}
    assert follow_client.post(reverse('followup_create', args=[follow_on.draft_id]), follow_data).status_code == 302
    follow_up = DealFollowUp.objects.get(deal_id=follow_on.draft_id)
    assert follow_client.post(reverse('followup_edit', args=[follow_on.draft_id, follow_up.pk]),
                              follow_data | {'completed': 'on'}).status_code == 302
    vendor = save_vendor(dealership=dealer, actor=owner, data={'name': 'Synthetic Restore Garage'})
    task = add_task(vehicle_id=vehicle.pk, dealership=dealer, actor=owner, data={
        'title': 'Synthetic restore repair', 'detail': 'Invented work', 'vendor': vendor,
        'assigned_to': staff, 'due_on': today, 'request_key': uuid4(),
    })
    cost_data = {'amount': Decimal('250.35'), 'category': 'repair', 'description': 'Synthetic original cost',
                 'effective_on': today, 'request_key': uuid4(), 'vendor': vendor, 'task': task}
    cost = add_cost(vehicle_id=vehicle.pk, dealership=dealer, actor=owner, data=cost_data)
    reversal = reverse_cost(vehicle_id=vehicle.pk, dealership=dealer, actor=owner, entry_id=cost.pk,
                            reason='Synthetic correction', request_key=uuid4())
    replacement = add_cost(vehicle_id=vehicle.pk, dealership=dealer, actor=owner,
        data=cost_data | {'amount': Decimal('40.10'), 'description': 'Synthetic replacement cost', 'request_key': uuid4()})
    assert reversal.reverses_id == cost.pk and replacement.vendor_name == 'Synthetic Restore Garage'
    save_vendor(dealership=dealer, actor=owner, vendor_id=vendor.pk,
                data={'name': 'Synthetic Restore Workshop', 'revision': vendor.revision})
    feedback_client = Client()
    feedback_client.force_login(staff)
    feedback_preview = feedback_client.post(reverse('feedback_create'), {
        'submission_key': str(uuid4()), 'kind': 'idea', 'area': 'inventory',
        'subject': 'Synthetic restore feedback', 'expected': 'Invented expected behavior',
        'actual': 'Invented improvement request', 'privacy_checked': 'on',
    })
    assert feedback_preview.status_code == 200 and not FeedbackReport.objects.exists()
    feedback_response = feedback_client.post(reverse('feedback_confirm'), {
        'preview_token': hidden_input(feedback_preview, 'preview_token'), 'action': 'save',
    })
    assert feedback_response.status_code == 302
    report = FeedbackReport.objects.get(dealership=dealer, author=staff)
    package_client = Client()
    package_client.force_login(owner)
    package_review = package_client.get(reverse('dealership_export_review'))
    assert package_review.status_code == 200
    package_response = package_client.post(reverse('dealership_export_download'), {
        'export_token': hidden_input(package_review, 'export_token'),
    })
    assert package_response.status_code == 200
    with zipfile.ZipFile(BytesIO(package_response.content)) as archive:
        feedback_bytes = archive.read('feedback.json')
        exported_feedback = json.loads(feedback_bytes)
        feedback_manifest = json.loads(archive.read('manifest.json'))['files']['feedback.json']
        assert feedback_manifest['bytes'] == len(feedback_bytes)
        assert feedback_manifest['sha256'] == hashlib.sha256(feedback_bytes).hexdigest()
    assert [row['id'] for row in exported_feedback['reports']] == [report.pk]
    package_event = DealershipExportEvent.objects.get(dealership=dealer, actor=owner)
    assert package_event.sha256 == hashlib.sha256(package_response.content).hexdigest()
    assert package_event.byte_size == len(package_response.content)
    (root / 'feedback-baseline.json').write_text(json.dumps(feedback_state(), sort_keys=True))
    (root / 'audit-baseline.json').write_text(json.dumps(audit_state(), sort_keys=True))
    (root / 'reconditioning-baseline.json').write_text(json.dumps(reconditioning_state(), sort_keys=True))
    (root / 'invoice-event-baseline.json').write_text(json.dumps(invoice_event_state(), sort_keys=True))
    (root / 'deal-file-event-baseline.json').write_text(json.dumps(deal_file_event_state(), sort_keys=True))
    (root / 'ledger-baseline.json').write_text(json.dumps(ledger_state(), sort_keys=True))
    (root / 'servicing-baseline.json').write_text(json.dumps(servicing_state(), sort_keys=True))
    (root / 'handoff-baseline.json').write_text(json.dumps(handoff_state(), sort_keys=True))
    (root / 'deal-baseline.json').write_text(json.dumps(deal_state(), sort_keys=True))
    print('Created invented feedback, activity, mock history, handoff, ledger, servicing, vehicle work, photo and PDFs.')


def verify():
    assert connection.vendor == 'postgresql'
    assert Dealership.objects.count() == 2 and Customer.objects.count() == 1
    assert Vehicle.objects.count() == 1 and DraftDeal.objects.count() == 4 and DealFile.objects.count() == 1
    item = DealFile.objects.get(title='Synthetic private file')
    assert item.deal.vehicle.stock_number == 'RESTORE-SYNTHETIC'
    assert item.deal.buyer.first_name == 'Synthetic'
    assert DealFileEvent.objects.filter(file=item, action='upload').count() == 1
    file_event_baseline = json.loads((root / 'deal-file-event-baseline.json').read_text())
    assert deal_file_event_state() == file_event_baseline and file_event_baseline
    def change_file_event(sql, event_id):
        with connection.cursor() as cursor:
            cursor.execute(sql, [event_id])
    for event in DealFileEvent.objects.filter(file=item).order_by('pk'):
        assert_guard_rejects('Deal file events are immutable',
            lambda: change_file_event("UPDATE documents_dealfileevent SET reason = 'changed' WHERE id = %s", event.pk))
        assert_guard_rejects('Deal file events are immutable',
            lambda: change_file_event('DELETE FROM documents_dealfileevent WHERE id = %s', event.pk))
    assert deal_file_event_state() == file_event_baseline
    baseline = json.loads((root / 'audit-baseline.json').read_text())
    assert len(baseline) == 6 and audit_state() == baseline
    audit = AuditEvent.objects.get(action='created')
    vehicle = item.deal.vehicle
    owner = get_user_model().objects.get(username='restore-exercise-owner')
    staff = get_user_model().objects.get(username='restore-exercise-staff')
    viewer = get_user_model().objects.get(username='restore-exercise-viewer')
    foreign_dealer = Dealership.objects.get(name='Synthetic foreign dealer')
    foreign = get_user_model().objects.get(username='restore-exercise-foreign')
    feedback_baseline = json.loads((root / 'feedback-baseline.json').read_text())
    assert feedback_state() == feedback_baseline
    report = FeedbackReport.objects.get(dealership=vehicle.dealership)
    package_event = DealershipExportEvent.objects.get(dealership=vehicle.dealership)
    assert report.author_id == staff.pk and report.subject == 'Synthetic restore feedback'
    assert package_event.actor_id == owner.pk and package_event.byte_size > 0 and len(package_event.sha256) == 64
    feedback_url = reverse('feedback_detail', args=[report.pk])
    feedback_client = Client()
    for user in (staff, owner):
        feedback_client.force_login(user)
        feedback_response = feedback_client.get(feedback_url)
        assert feedback_response.status_code == 200 and b'Synthetic restore feedback' in feedback_response.content
        assert 'no-store' in feedback_response['Cache-Control']
    for user in (viewer, foreign):
        feedback_client.force_login(user)
        assert feedback_client.get(feedback_url).status_code == 404
    own_feedback = export_feedback(dealership_id=vehicle.dealership_id, actor=owner)
    foreign_feedback = export_feedback(dealership_id=foreign_dealer.pk, actor=foreign)
    assert [row['id'] for row in own_feedback['reports']] == [report.pk] and not foreign_feedback['reports']
    try:
        export_feedback(dealership_id=vehicle.dealership_id, actor=staff)
    except PermissionDenied:
        pass
    else:
        raise AssertionError('Non-owner unexpectedly exported dealership feedback')
    assert_guard_rejects('Dealership export audit is immutable',
                         lambda: DealershipExportEvent.objects.filter(pk=package_event.pk).update(byte_size=1))
    assert_guard_rejects('Dealership export audit is immutable',
                         lambda: DealershipExportEvent.objects.filter(pk=package_event.pk).delete())
    assert feedback_state() == feedback_baseline
    reconditioning_baseline = json.loads((root / 'reconditioning-baseline.json').read_text())
    assert reconditioning_state() == reconditioning_baseline
    vendor = VehicleVendor.objects.get(name='Synthetic Restore Workshop')
    task = ReconTask.objects.get(vehicle=vehicle)
    original = VehicleCostEntry.objects.get(vehicle=vehicle, kind='cost', description='Synthetic original cost')
    replacement = VehicleCostEntry.objects.get(vehicle=vehicle, description='Synthetic replacement cost')
    reversal = VehicleCostEntry.objects.get(vehicle=vehicle, kind='reversal')
    assert vendor.created_by_id == owner.pk and vendor.events.count() == 2
    def change_vendor_event(sql, event_id):
        with connection.cursor() as cursor:
            cursor.execute(sql, [event_id])
    for event in vendor.events.order_by('pk'):
        assert_guard_rejects('Vendor events are immutable',
            lambda: change_vendor_event("UPDATE inventory_vehiclevendorevent SET changes = '{}'::jsonb WHERE id = %s", event.pk))
        assert_guard_rejects('Vendor events are immutable',
            lambda: change_vendor_event('DELETE FROM inventory_vehiclevendorevent WHERE id = %s', event.pk))
    assert reconditioning_state() == reconditioning_baseline
    assert task.vendor_id == vendor.pk and task.assigned_to_id == staff.pk
    assert original.vendor_id == replacement.vendor_id == vendor.pk and original.task_id == replacement.task_id == task.pk
    assert original.vendor_name == replacement.vendor_name == reversal.vendor_name == 'Synthetic Restore Garage'
    assert reversal.reverses_id == original.pk and reversal.amount_cents == original.amount_cents == 25035
    assert reversal.vendor_id == vendor.pk and reversal.task_id == task.pk and reversal.actor_id == owner.pk
    assert (original.debit, original.credit, reversal.debit, reversal.credit) == ('vehicle_cost', 'cost_offset', 'cost_offset', 'vehicle_cost')
    assert replacement.amount_cents == 4010 and with_cost_totals(Vehicle.objects.filter(pk=vehicle.pk)).get().registered_cost_cents == 4010
    recon_url = reverse('vehicle_recon', args=[vehicle.pk])
    vendor_url = reverse('vendor_detail', args=[vendor.pk])
    recon_client = Client()
    recon_client.force_login(foreign)
    assert recon_client.get(recon_url).status_code == 404 and recon_client.get(vendor_url).status_code == 404
    for user in (owner, staff, viewer):
        recon_client.force_login(user)
        recon_response = recon_client.get(recon_url)
        assert recon_response.status_code == 200 and b'Synthetic restore repair' in recon_response.content
        assert b'Synthetic Restore Garage' in recon_response.content and b'40.10' in recon_response.content
        assert 'no-store' in recon_response['Cache-Control']
        vendor_response = recon_client.get(vendor_url)
        assert vendor_response.status_code == 200 and b'Synthetic Restore Workshop' in vendor_response.content
    assert reconditioning_state() == reconditioning_baseline and audit_state() == baseline
    activity_baseline = json.loads((root / 'customer-activity-baseline.json').read_text())
    assert customer_activity_state() == activity_baseline
    activity = CustomerActivity.objects.get(customer=item.deal.buyer)
    assert activity.detail == 'Synthetic restore follow-up' and activity.assigned_to_id == staff.pk
    assert activity.completed_by_id == owner.pk and activity.completed_at is not None and activity.revision == 2
    assert CustomerEvent.objects.filter(customer=activity.customer).count() == 2
    def change_customer_event(sql, event_id):
        with connection.cursor() as cursor:
            cursor.execute(sql, [event_id])
    for event in CustomerEvent.objects.filter(customer=activity.customer).order_by('pk'):
        assert_guard_rejects('Customer events are immutable',
            lambda: change_customer_event("UPDATE customers_customerevent SET changes = '{}'::jsonb WHERE id = %s", event.pk))
        assert_guard_rejects('Customer events are immutable',
            lambda: change_customer_event('DELETE FROM customers_customerevent WHERE id = %s', event.pk))
    assert customer_activity_state() == activity_baseline
    activity_url = reverse('customer_activity_history', args=[activity.customer_id])
    activity_client = Client()
    activity_client.force_login(foreign)
    assert activity_client.get(activity_url).status_code == 404
    for user in (owner, staff, viewer):
        activity_client.force_login(user)
        activity_response = activity_client.get(activity_url)
        assert activity_response.status_code == 200 and b'Synthetic restore follow-up' in activity_response.content
        assert 'no-store' in activity_response['Cache-Control']
    submission = MockMessageSubmission.objects.get(dealership=vehicle.dealership)
    assert submission.actor_id == staff.pk and submission.events.count() == 2
    with override_settings(DEMO_MESSAGE_SIMULATOR_ENABLED=True):
        for user in (owner, staff):
            assert mock_status(dealership_id=vehicle.dealership_id, actor=user, submission_id=submission.submission_id) == 'mock-delivered'
        try:
            mock_status(dealership_id=vehicle.dealership_id, actor=viewer, submission_id=submission.submission_id)
        except PermissionDenied:
            pass
        else:
            raise AssertionError('Viewer unexpectedly accessed the mock simulator')
        try:
            mock_status(dealership_id=foreign_dealer.pk, actor=foreign, submission_id=submission.submission_id)
        except Http404:
            pass
        else:
            raise AssertionError('Foreign dealership unexpectedly accessed mock history')
    own_export = export_customers(dealership_id=vehicle.dealership_id, actor=owner)
    foreign_export = export_customers(dealership_id=foreign_dealer.pk, actor=foreign)
    assert [row['id'] for row in own_export['activities']] == [activity.pk]
    assert {row['id'] for row in own_export['events']} == set(CustomerEvent.objects.values_list('pk', flat=True))
    assert [row['id'] for row in own_export['mock_message_submissions']] == [submission.pk]
    assert {row['id'] for row in own_export['mock_message_events']} == set(submission.events.values_list('pk', flat=True))
    assert not foreign_export['activities'] and not foreign_export['mock_message_submissions'] and not foreign_export['mock_message_events']
    assert customer_activity_state() == activity_baseline
    packet = DemoDealPacket.objects.get(deal=item.deal)
    packet_baseline = json.loads((root / 'packet-baseline.json').read_text())
    def packet_state():
        return json.loads(json.dumps(list(DemoDealPacket.objects.filter(pk=packet.pk).values()), cls=DjangoJSONEncoder, sort_keys=True))
    assert packet_state() == packet_baseline
    packet_export_baseline = json.loads((root / 'packet-export-event-baseline.json').read_text())
    assert packet_export_event_state() == packet_export_baseline
    assert len(packet_export_baseline) == 1
    packet_export_event = DemoPacketExportEvent.objects.get(packet=packet)
    assert packet_export_event.actor_id == owner.pk
    def change_packet_export_event(sql):
        with connection.cursor() as cursor:
            cursor.execute(sql, [packet_export_event.pk])
    assert_guard_rejects('Packet export events are immutable',
        lambda: change_packet_export_event("UPDATE documents_demopacketexportevent SET bundle_sha256 = 'changed' WHERE id = %s"))
    assert_guard_rejects('Packet export events are immutable',
        lambda: change_packet_export_event('DELETE FROM documents_demopacketexportevent WHERE id = %s'))
    assert packet_export_event_state() == packet_export_baseline
    assert digest(packet.html) == packet.artifact_sha256 and source_digest(packet.snapshot) == packet.source_sha256
    assert packet.template_version in packet.html and REGISTRY_VERSION in packet.html
    packet_url = reverse('demo_packet_artifact', args=[item.deal_id, packet.pk])
    packet_client = Client()
    packet_client.force_login(get_user_model().objects.get(username='restore-exercise-foreign'))
    assert packet_client.get(packet_url).status_code == 404
    packet_client.force_login(owner)
    response = packet_client.get(packet_url)
    assert response.status_code == 200 and response.content == packet.html.encode('utf-8')
    assert 'no-store' in response['Cache-Control']
    handoff_baseline = json.loads((root / 'handoff-baseline.json').read_text())
    assert handoff_state() == handoff_baseline
    deal_baseline = json.loads((root / 'deal-baseline.json').read_text())
    assert deal_state() == deal_baseline
    handoff_context = DemoAccountContext.objects.select_related('book').get()
    completion = DemoDealCompletion.objects.select_related('deal', 'packet').get(deal_id=handoff_context.deal_id)
    restored_trade = DraftTradeIn.objects.get(deal=completion.deal)
    assert restored_trade.vin == 'SYNTHETIC-RESTORE-TRADE' and restored_trade.title_brand == 'rebuilt'
    assert restored_trade.odometer_reading == 123456 and restored_trade.odometer_status == 'not_actual'
    assert completion.deal.trade_allowance == Decimal('1500.00') and completion.deal.trade_payoff == Decimal('250.00')
    trade_event = DealEvent.objects.get(deal=completion.deal, snapshot__action='trade_saved')
    assert trade_event.actor_id == owner.pk and trade_event.snapshot['revision'] == completion.source_revision
    assert trade_event.snapshot['trades'][0]['id'] == restored_trade.pk
    assert trade_event.snapshot['trades'][0]['title_brand'] == 'rebuilt'
    assert trade_event.snapshot['trades'][0]['odometer_status'] == 'not_actual'
    assert trade_event.snapshot['trade_allowance'] == '1500.00' and trade_event.snapshot['trade_payoff'] == '250.00'
    frozen_trade = verified_snapshot(completion)['trade']
    assert frozen_trade['record_id'] == restored_trade.pk and frozen_trade['facts']['VIN'] == restored_trade.vin
    assert frozen_trade['facts']['Title brand as recorded'] == restored_trade.get_title_brand_display()
    assert frozen_trade['facts']['Mileage status as recorded'] == restored_trade.get_odometer_status_display()
    assert handoff_context.snapshot['source'] == 'completed-rehearsal'
    assert handoff_context.snapshot['completion_id'] == completion.pk
    assert handoff_context.snapshot['completion_review_sha256'] == completion.review_sha256
    assert handoff_context.snapshot['deal_revision'] == completion.source_revision
    assert handoff_context.snapshot_sha256 == result_digest(handoff_context.snapshot)
    assert handoff_context.book.dealership_id == vehicle.dealership_id and handoff_context.book.customer_id == item.deal.buyer_id
    assert handoff_context.created_by_id == owner.pk and handoff_context.book.postings.get(kind='opening').amount_cents == 1000025
    assert verified_snapshot(completion) == completion.packet.snapshot
    assert result_digest(completed_account_snapshot(completion.deal)) == handoff_context.snapshot_sha256
    handoff_url = reverse('bhph_account', args=[handoff_context.book_id])
    completion_url = reverse('deal_completion', args=[completion.deal_id])
    handoff_client = Client()
    handoff_client.force_login(get_user_model().objects.get(username='restore-exercise-foreign'))
    assert handoff_client.get(handoff_url).status_code == 404
    assert handoff_client.get(completion_url).status_code == 404
    for user in (owner, get_user_model().objects.get(username='restore-exercise-viewer')):
        handoff_client.force_login(user)
        handoff_response = handoff_client.get(handoff_url)
        assert handoff_response.status_code == 200 and b'completed rehearsal' in handoff_response.content
        assert 'no-store' in handoff_response['Cache-Control']
        completion_response = handoff_client.get(completion_url)
        assert completion_response.status_code == 200 and 'no-store' in completion_response['Cache-Control']
    void = DemoCompletionVoid.objects.select_related('completion__packet').get()
    follow_on = DemoFollowOnDraft.objects.select_related('draft').get(void_rehearsal=void)
    follow_up = DealFollowUp.objects.get(deal=follow_on.draft)
    assert verified_snapshot(void.completion) == void.completion.packet.snapshot
    _, restored_void_digest, restored_void = preview_void(dealership_id=vehicle.dealership_id,
        deal_id=void.completion.deal_id, actor=owner)
    assert restored_void.pk == void.pk and restored_void_digest == void.review_sha256
    assert preview_follow_on_draft(dealership_id=vehicle.dealership_id,
        deal_id=void.completion.deal_id, actor=owner)['prior'].pk == follow_on.pk
    assert preview_void(dealership_id=vehicle.dealership_id,
        deal_id=void.completion.deal_id, actor=staff)[2].pk == void.pk
    assert preview_follow_on_draft(dealership_id=vehicle.dealership_id,
        deal_id=void.completion.deal_id, actor=staff)['prior'].pk == follow_on.pk
    for check in (preview_void, preview_follow_on_draft):
        try:
            check(dealership_id=vehicle.dealership_id, deal_id=void.completion.deal_id, actor=viewer)
        except PermissionDenied:
            pass
        else:
            raise AssertionError('Viewer unexpectedly accessed editor-only provenance preview')
        try:
            check(dealership_id=foreign_dealer.pk, deal_id=void.completion.deal_id, actor=foreign)
        except Http404:
            pass
        else:
            raise AssertionError('Foreign dealership unexpectedly accessed provenance preview')
    follow_event = DealEvent.objects.get(deal=follow_on.draft, snapshot__action='follow_on_draft_created')
    provenance = follow_event.snapshot['follow_on_provenance']
    assert provenance['source_completion_id'] == void.completion_id and provenance['source_void_id'] == void.pk
    assert provenance['source_packet_id'] == void.completion.packet_id and provenance['source_review_sha256'] == void.completion.review_sha256
    assert provenance['void_review_sha256'] == void.review_sha256 and provenance['follow_on_review_sha256'] == follow_on.review_sha256
    assert provenance['synthetic_only'] and provenance['money_copied'] and follow_on.draft.sale_price == Decimal('3500.00')
    assert follow_up.assigned_to_id == staff.pk and follow_up.completed_by_id == owner.pk and follow_up.revision == 2
    assert set(follow_up.events.values_list('action', flat=True)) == {'created', 'completed'}
    follow_up_url = reverse('followup_detail', args=[follow_up.pk])
    follow_draft_url = reverse('deal_detail', args=[follow_on.draft_id])
    void_source_url = reverse('deal_completion', args=[void.completion.deal_id])
    follow_client = Client()
    follow_client.force_login(foreign)
    assert all(follow_client.get(url).status_code == 404 for url in (follow_up_url, follow_draft_url, void_source_url))
    for user in (owner, staff, viewer):
        follow_client.force_login(user)
        response = follow_client.get(follow_up_url)
        assert response.status_code == 200 and b'Synthetic deal follow-up' in response.content
        assert 'no-store' in response['Cache-Control']
        assert follow_client.get(follow_draft_url).status_code == 200
        assert follow_client.get(void_source_url).status_code == 200
    def change_provenance(sql, pk):
        with connection.cursor() as cursor:
            cursor.execute(sql, [pk])
    assert not DemoDealCompletion.objects.filter(deal_id=follow_on.draft_id).exists()
    draft_event = DealEvent.objects.filter(deal_id=follow_on.draft_id).earliest('pk')
    for event, message in (
        (draft_event, 'Deal events are immutable'),
        # PostgreSQL runs the earlier-named completion trigger first.
        (trade_event, 'Completed rehearsal source is frozen'),
    ):
        assert_guard_rejects(message,
            lambda: change_provenance("UPDATE deals_dealevent SET snapshot = '{}'::jsonb WHERE id = %s", event.pk))
        assert_guard_rejects(message,
            lambda: change_provenance('DELETE FROM deals_dealevent WHERE id = %s', event.pk))
    assert deal_state() == deal_baseline
    for sql, pk, message in (
        ("UPDATE deals_democompletionvoid SET reason = 'changed' WHERE id = %s", void.pk, 'Void rehearsal is immutable'),
        ('DELETE FROM deals_democompletionvoid WHERE id = %s', void.pk, 'Void rehearsal is immutable'),
        ("UPDATE deals_demofollowondraft SET reason = 'changed' WHERE id = %s", follow_on.pk, 'Follow-on draft provenance is immutable'),
        ('DELETE FROM deals_demofollowondraft WHERE id = %s', follow_on.pk, 'Follow-on draft provenance is immutable'),
    ):
        assert_guard_rejects(message, lambda: change_provenance(sql, pk))
    for event in follow_up.events.all():
        assert_guard_rejects('Deal follow-up events are immutable',
            lambda: change_provenance("UPDATE deals_followupevent SET action = 'changed' WHERE id = %s", event.pk))
        assert_guard_rejects('Deal follow-up events are immutable',
            lambda: change_provenance('DELETE FROM deals_followupevent WHERE id = %s', event.pk))
    assert deal_state() == deal_baseline and handoff_state() == handoff_baseline
    with transaction.atomic():
        Customer.objects.filter(pk=item.deal.buyer_id).update(first_name='Changed synthetic')
        assert packet_source(dealership_id=vehicle.dealership_id, deal_id=item.deal_id) != packet.snapshot
        assert packet_client.get(packet_url).content == packet.html.encode('utf-8')
        assert packet_state() == packet_baseline
        assert handoff_state() == handoff_baseline
        assert packet_source(dealership_id=vehicle.dealership_id, deal_id=completion.deal_id) != completion.packet.snapshot
        refreshed_deal = DraftDeal.objects.get(pk=completion.deal_id)
        assert result_digest(completed_account_snapshot(refreshed_deal)) == handoff_context.snapshot_sha256
        transaction.set_rollback(True)
    assert packet_state() == packet_baseline
    assert handoff_state() == handoff_baseline
    assert deal_state() == deal_baseline
    assert audit.dealership_id == vehicle.dealership_id and audit.actor_id == owner.pk
    # A valid new audit is accepted, but rolled back so verification retains the
    # exact restored history. Each negative check also has its own transaction.
    with transaction.atomic():
        AuditEvent.objects.create(dealership=vehicle.dealership, vehicle=vehicle, actor=owner,
                                  action='synthetic valid guard check', changes={})
        transaction.set_rollback(True)
    assert_guard_rejects('Invalid inventory audit scope', lambda: AuditEvent.objects.create(
        dealership=foreign_dealer, vehicle=vehicle, actor=owner, action='invalid', changes={}))
    assert_guard_rejects('Inventory audit history is append-only',
                         lambda: AuditEvent.objects.filter(pk=audit.pk).update(action='changed'))
    assert_guard_rejects('Inventory audit history is append-only',
                         lambda: AuditEvent.objects.filter(pk=audit.pk).delete())
    assert_guard_rejects('Vehicle with audit history cannot change dealership',
                         lambda: Vehicle.objects.filter(pk=vehicle.pk).update(dealership=foreign_dealer))
    assert audit_state() == baseline
    ledger_baseline = json.loads((root / 'ledger-baseline.json').read_text())
    assert ledger_state() == ledger_baseline
    book = DemoBook.objects.get(label='Synthetic restore account')
    postings = list(book.postings.order_by('pk'))
    assert len(postings) == 3 and [entry.kind for entry in postings] == ['opening', 'receipt', 'reversal']
    opening, receipt, reversal = postings
    assert book.dealership_id == vehicle.dealership_id and book.customer_id == item.deal.buyer_id
    assert book.created_by_id == owner.pk and all(entry.actor_id == owner.pk for entry in postings)
    assert opening.amount_cents == 1000025 and receipt.amount_cents == reversal.amount_cents == 12550
    assert (opening.debit, opening.credit) == ('principal', 'opening_offset')
    assert (receipt.debit, receipt.credit) == ('cash_control', 'unapplied')
    assert (reversal.debit, reversal.credit, reversal.reverses_id) == ('unapplied', 'cash_control', receipt.pk)
    assert receipt.payment_method == reversal.payment_method == 'cash'
    totals = reconcile(dealership_id=vehicle.dealership_id, book_id=book.pk)
    assert totals['balanced'] and totals['opening_entries'] == 1
    assert totals['total_debits_cents'] == totals['total_credits_cents'] == 1025125
    assert totals['net_debit'] == {'principal': 1000025, 'opening_offset': -1000025,
                                   'cash_control': 0, 'unapplied': 0}
    servicing_baseline = json.loads((root / 'servicing-baseline.json').read_text())
    assert servicing_state() == servicing_baseline
    schedule = DemoSchedule.objects.get(book=book)
    plan = DemoServicingPlan.objects.get(book=book)
    assert plan.schedule_id == schedule.pk and plan.schedule_sha256 == result_digest(schedule.result)
    projection = projection_for_book(book, as_of=book.opening_on)
    assert projection['status'] == 'current' and projection['amount_due_cents'] == 0
    assert projection['remaining_scheduled_cents'] == 1020000 and projection['net_receipts_cents'] == 0
    assert [row['scheduled_cents'] for row in projection['rows']] == [340000, 340000, 340000]
    assert projection['next_unpaid_on'] == (book.opening_on + timedelta(days=1)).isoformat()
    servicing_url = reverse('servicing_detail', args=[book.pk])
    servicing_client = Client()
    servicing_client.force_login(get_user_model().objects.get(username='restore-exercise-foreign'))
    assert servicing_client.get(servicing_url, {'as_of': book.opening_on.isoformat()}).status_code == 404
    servicing_client.force_login(owner)
    servicing_response = servicing_client.get(servicing_url, {'as_of': book.opening_on.isoformat()})
    assert servicing_response.status_code == 200 and b'Demo installment coverage' in servicing_response.content
    assert all(text in servicing_response.content for text in (b'Demo up to date', b'10,200.00', b'3,400.00'))
    assert 'no-store' in servicing_response['Cache-Control']
    assert servicing_state() == servicing_baseline and ledger_state() == ledger_baseline
    def ledger_sql(sql, pk):
        with connection.cursor() as cursor:
            cursor.execute(sql, [pk])
    for sql, pk in (
        ("UPDATE finance_demobook SET label = 'changed' WHERE id = %s", book.pk),
        ('DELETE FROM finance_demobook WHERE id = %s', book.pk),
        ("UPDATE finance_demoposting SET reason = 'changed' WHERE id = %s", receipt.pk),
        ('DELETE FROM finance_demoposting WHERE id = %s', receipt.pk),
    ):
        assert_guard_rejects('Synthetic ledger records are append-only', lambda: ledger_sql(sql, pk))
    assert ledger_state() == ledger_baseline
    with item.blob.open('rb') as source:
        data = source.read()
    assert data == PDF and hashlib.sha256(data).hexdigest() == item.sha256
    try:
        item.blob.url
    except ValueError:
        pass
    else:
        raise AssertionError('Private storage exposed a URL')
    url = reverse('deal_file_download', args=[item.deal_id, item.pk])
    client = Client()
    client.force_login(get_user_model().objects.get(username='restore-exercise-foreign'))
    assert client.get(url).status_code == 404
    client.force_login(get_user_model().objects.get(username='restore-exercise-owner'))
    response = client.get(url)
    assert response.status_code == 200 and b''.join(response.streaming_content) == PDF
    assert 'no-store' in response['Cache-Control'] and 'attachment' in response['Content-Disposition']
    assert DealFileEvent.objects.filter(file=item, action='download').count() == 1

    photo = VehiclePhoto.objects.get(vehicle=vehicle)
    invoice = VehicleInvoice.objects.get(vehicle=vehicle, title='Synthetic vehicle invoice')
    acquisition = VehicleAcquisitionFile.objects.get(vehicle=vehicle, title='Synthetic acquisition PDF')
    assert invoice.cost_id is None and acquisition.description == 'Unverified synthetic document'
    assert VehicleInvoiceEvent.objects.filter(invoice=invoice, action='upload').count() == 1
    invoice_event_baseline = json.loads((root / 'invoice-event-baseline.json').read_text())
    assert invoice_event_state() == invoice_event_baseline and invoice_event_baseline
    def change_invoice_event(sql, event_id):
        with connection.cursor() as cursor:
            cursor.execute(sql, [event_id])
    for event in VehicleInvoiceEvent.objects.filter(invoice=invoice).order_by('pk'):
        assert_guard_rejects('Invoice events are immutable',
            lambda: change_invoice_event("UPDATE documents_vehicleinvoiceevent SET action = 'download' WHERE id = %s", event.pk))
        assert_guard_rejects('Invoice events are immutable',
            lambda: change_invoice_event('DELETE FROM documents_vehicleinvoiceevent WHERE id = %s', event.pk))
    assert invoice_event_state() == invoice_event_baseline
    assert VehicleAcquisitionFileEvent.objects.filter(file=acquisition, action='upload').count() == 1
    artifacts = (
        (photo.image, (root / 'expected-photo.jpg').read_bytes(), reverse('vehicle_photo_file', args=[photo.pk]), None),
        (photo.thumbnail, (root / 'expected-thumbnail.jpg').read_bytes(), reverse('vehicle_photo_thumbnail', args=[photo.pk]), None),
        (invoice.blob, INVOICE_PDF, reverse('vehicle_invoice_download', args=[vehicle.pk, invoice.pk]), invoice.sha256),
        (acquisition.blob, ACQUISITION_PDF, reverse('vehicle_acquisition_file_download', args=[vehicle.pk, acquisition.pk]), acquisition.sha256),
    )
    for field, expected, artifact_url, stored_sha256 in artifacts:
        with field.open('rb') as source:
            restored = source.read()
        assert restored == expected and hashlib.sha256(restored).digest() == hashlib.sha256(expected).digest()
        if stored_sha256 is not None:
            assert hashlib.sha256(restored).hexdigest() == stored_sha256
        try:
            field.url
        except ValueError:
            pass
        else:
            raise AssertionError('Private vehicle artifact exposed a URL')
        client.force_login(get_user_model().objects.get(username='restore-exercise-foreign'))
        assert client.get(artifact_url).status_code == 404
        client.force_login(owner)
        response = client.get(artifact_url)
        assert response.status_code == 200 and 'no-store' in response['Cache-Control']
        content = b''.join(response.streaming_content) if response.streaming else response.content
        assert content == expected
        response.close()
    assert VehicleInvoiceEvent.objects.filter(invoice=invoice, action='download').count() == 1
    assert VehicleAcquisitionFileEvent.objects.filter(file=acquisition, action='download').count() == 1
    assert customer_activity_state() == activity_baseline
    assert reconditioning_state() == reconditioning_baseline and audit_state() == baseline
    assert feedback_state() == feedback_baseline
    assert deal_state() == deal_baseline
    print('Verified feedback, export audit, activity, mock history, deal/trade history, void/follow-on, follow-up, handoff, ledger, servicing, reconditioning, artifacts, guards and scoped access.')


(seed if mode == 'seed' else verify)()

# SPDX-License-Identifier: MPL-2.0
"""Seed or verify only the disposable cluster created by restore_exercise.py."""
import hashlib
import json
import os
from io import BytesIO
from pathlib import Path
import sys
from uuid import uuid4

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
from django.core.serializers.json import DjangoJSONEncoder
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from core.models import AuditEvent, Dealership, Membership
from customers.models import Customer
from inventory.models import Vehicle, VehiclePhoto
from inventory.photos import add_photos, normalize_photo
from deals.models import DraftDeal
from finance.models import DemoBook, DemoPosting
from finance.services import open_book, record_receipt, reverse_receipt, reconcile
from documents.models import (DealFile, DealFileEvent, VehicleInvoice,
                              VehicleInvoiceEvent, VehicleAcquisitionFile,
                              VehicleAcquisitionFileEvent)
from documents.invoice_views import upload_invoice
from documents.acquisition_views import upload_acquisition_file
from documents.services import upload_deal_file
from documents.models import DemoDealPacket
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
    foreign = get_user_model().objects.create_user('restore-exercise-foreign')
    Membership.objects.create(user=owner, dealership=dealer, role='owner')
    Membership.objects.create(user=foreign, dealership=foreign_dealer, role='owner')
    buyer = Customer.objects.create(dealership=dealer, first_name='Synthetic', last_name='Restore')
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
    (root / 'audit-baseline.json').write_text(json.dumps(audit_state(), sort_keys=True))
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
    (root / 'ledger-baseline.json').write_text(json.dumps(ledger_state(), sort_keys=True))
    print('Created invented records, synthetic ledger, vehicle photo and private PDFs.')


def verify():
    assert connection.vendor == 'postgresql'
    assert Dealership.objects.count() == 2 and Customer.objects.count() == 1
    assert Vehicle.objects.count() == 1 and DraftDeal.objects.count() == 1 and DealFile.objects.count() == 1
    item = DealFile.objects.get(title='Synthetic private file')
    assert item.deal.vehicle.stock_number == 'RESTORE-SYNTHETIC'
    assert item.deal.buyer.first_name == 'Synthetic'
    assert DealFileEvent.objects.filter(file=item, action='upload').count() == 1
    baseline = json.loads((root / 'audit-baseline.json').read_text())
    assert len(baseline) == 2 and audit_state() == baseline
    audit = AuditEvent.objects.get(action='created')
    vehicle = item.deal.vehicle
    owner = get_user_model().objects.get(username='restore-exercise-owner')
    foreign_dealer = Dealership.objects.get(name='Synthetic foreign dealer')
    packet = DemoDealPacket.objects.get(deal=item.deal)
    packet_baseline = json.loads((root / 'packet-baseline.json').read_text())
    def packet_state():
        return json.loads(json.dumps(list(DemoDealPacket.objects.filter(pk=packet.pk).values()), cls=DjangoJSONEncoder, sort_keys=True))
    assert packet_state() == packet_baseline
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
    with transaction.atomic():
        Customer.objects.filter(pk=item.deal.buyer_id).update(first_name='Changed synthetic')
        assert packet_source(dealership_id=vehicle.dealership_id, deal_id=item.deal_id) != packet.snapshot
        assert packet_client.get(packet_url).content == packet.html.encode('utf-8')
        assert packet_state() == packet_baseline
        transaction.set_rollback(True)
    assert packet_state() == packet_baseline
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
    print('Verified frozen packet, ledger records, balances, reversal and append-only guards; audit guards, private artifacts, hashes, and scoped downloads.')


(seed if mode == 'seed' else verify)()

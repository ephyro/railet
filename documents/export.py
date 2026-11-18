# SPDX-License-Identifier: MPL-2.0
"""Internal synthetic documents export, not a complete backup or delivery API.

Includes DealFile/DealFileEvent, DemoDealPacket/DemoPacketExportEvent and
VehicleInvoice/VehicleInvoiceEvent, including archived deal files. Private PDFs
and saved packet HTML are original bytes; packet snapshots and all document-owned
metadata/history are in metadata.json. Deals, customers, vehicles, costs, users,
other module files and orphaned storage objects are excluded. IDs are references.
Prior packet-export events retain hashes, not the historical ZIP bytes; those
previously delivered ZIPs cannot be reconstructed exactly from audit events.

The returned ZIP is unencrypted and contains unredacted private information.
This service has no endpoint, delivery audit, import or restore function. Callers
must enforce equivalent authorization and record delivery before releasing it.
DB queries and separate file reads do not form a point-in-time snapshot: quiesce
writers and storage changes or use a separately reviewed coordinated snapshot.
Privileged DB/filesystem changes and runtime schema changes can bypass checks.
"""
import hashlib
import io
import json
import posixpath
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from uuid import UUID
import zipfile
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from core.models import Membership
from .models import (DealFile, DealFileEvent, DemoDealPacket, DemoPacketExportEvent,
                     VehicleAcquisitionFile, VehicleAcquisitionFileEvent,
                     VehicleInvoice, VehicleInvoiceEvent)
from .packets import source_digest

FORMAT_VERSION = 'railet-synthetic-documents-v1'
MAX_RECORDS = 10000
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


class DocumentsExportError(Exception):
    """No partial package may be returned when validation fails."""


def _convert(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _convert(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_convert(item) for item in value]
    return value


def _records(query):
    rows = list(query.order_by('pk')[:MAX_RECORDS + 1])
    if len(rows) > MAX_RECORDS:
        raise DocumentsExportError('Document export exceeds the record limit; no package prepared.')
    return rows


def _metadata(instance, *, omit=()):
    row = {}
    for field in instance._meta.concrete_fields:
        if field.name in omit:
            continue
        value = getattr(instance, field.attname)
        if field.name == 'blob':
            value = value.name
        row[field.attname] = _convert(value)
    return row


def _artifact(file_record, prefix):
    name = file_record.blob.name
    path = PurePosixPath(name or '')
    if (not name or '\\' in name or str(path) != name or path.is_absolute() or len(path.parts) != 2
            or path.parts[0] != prefix or path.parts[1] in ('.', '..')):
        raise DocumentsExportError('A document has an invalid private storage reference; no package prepared.')
    if file_record.byte_size > MAX_ARTIFACT_BYTES:
        raise DocumentsExportError('An artifact exceeds the file size limit; no package prepared.')
    try:
        storage = file_record.blob.storage
        base = Path(storage.location).resolve(strict=True)
        raw = Path(storage.path(name))
        resolved = raw.resolve(strict=True)
        if not resolved.is_relative_to(base) or raw.is_symlink() or raw.parent.is_symlink():
            raise DocumentsExportError('A document points outside private storage; no package prepared.')
        with file_record.blob.open('rb') as source:
            content = source.read(MAX_ARTIFACT_BYTES + 1)
    except (OSError, ValueError) as error:
        raise DocumentsExportError('A private artifact is missing or inaccessible; no package prepared.') from error
    if len(content) != file_record.byte_size or hashlib.sha256(content).hexdigest() != file_record.sha256:
        raise DocumentsExportError('A private artifact failed its size or hash check; no package prepared.')
    return content


@transaction.atomic
def export_documents(*, dealership_id, actor):
    """Return one verified ZIP for an active owner, under all synthetic gates."""
    if not all(getattr(settings, flag, False) for flag in
               ('DEBUG', 'DEAL_FILES_DEMO_ENABLED', 'DEMO_PACKETS_ENABLED', 'RECON_DEMO_ENABLED')):
        raise PermissionDenied('Synthetic documents export is disabled.')
    if not getattr(actor, 'is_authenticated', False) or not getattr(actor, 'pk', None):
        raise PermissionDenied
    if not Membership.objects.select_for_update().filter(user_id=actor.pk, user__is_active=True,
            dealership_id=dealership_id, role=Membership.Role.OWNER).exists():
        raise PermissionDenied
    started = timezone.now()
    deal_scope = Q(deal__dealership_id=dealership_id)
    valid_deal = (Q(deal__vehicle__dealership_id=dealership_id) & Q(deal__buyer__dealership_id=dealership_id)
                  & (Q(deal__co_buyer__isnull=True) | Q(deal__co_buyer__dealership_id=dealership_id)))
    for model in (DealFile, DemoDealPacket):
        if model.objects.filter(deal_scope).exclude(valid_deal).exists():
            raise DocumentsExportError('A document references an out-of-scope deal; no package prepared.')
    if VehicleInvoice.objects.filter(vehicle__dealership_id=dealership_id, cost__isnull=False).exclude(
            cost__vehicle_id=F('vehicle_id')).exists():
        raise DocumentsExportError('An invoice references a different vehicle cost; no package prepared.')
    files = _records(DealFile.objects.filter(deal_scope))
    packets = _records(DemoDealPacket.objects.filter(deal_scope))
    invoices = _records(VehicleInvoice.objects.filter(vehicle__dealership_id=dealership_id))
    acquisition_files = _records(VehicleAcquisitionFile.objects.filter(vehicle__dealership_id=dealership_id))
    file_names = [record.blob.name for record in files]
    invoice_names = [record.blob.name for record in invoices]
    acquisition_names = [record.blob.name for record in acquisition_files]
    # A stored alias such as "deal-files/./a.pdf" resolves to the same file as
    # "deal-files/a.pdf". Compare normalized foreign names before opening any
    # scoped file; exact string comparisons miss aliases on either side.
    for model, foreign_scope, local_names in (
        (DealFile, {'deal__dealership_id': dealership_id}, file_names),
        (VehicleInvoice, {'vehicle__dealership_id': dealership_id}, invoice_names),
        (VehicleAcquisitionFile, {'vehicle__dealership_id': dealership_id}, acquisition_names),
    ):
        local = {posixpath.normpath(name) for name in local_names if name}
        if local:
            for foreign in model.objects.exclude(**foreign_scope).values_list('blob', flat=True).iterator(chunk_size=1000):
                if foreign and posixpath.normpath(foreign) in local:
                    raise DocumentsExportError('A private storage reference is shared across dealerships; no package prepared.')
    file_events = _records(DealFileEvent.objects.filter(file__deal__dealership_id=dealership_id))
    packet_events = _records(DemoPacketExportEvent.objects.filter(packet__deal__dealership_id=dealership_id))
    invoice_events = _records(VehicleInvoiceEvent.objects.filter(invoice__vehicle__dealership_id=dealership_id))
    acquisition_events = _records(VehicleAcquisitionFileEvent.objects.filter(file__vehicle__dealership_id=dealership_id))
    parts = {}
    artifact_total = 0
    def add(name, content):
        nonlocal artifact_total
        artifact_total += len(content)
        if len(content) > MAX_ARTIFACT_BYTES or artifact_total > MAX_TOTAL_BYTES:
            raise DocumentsExportError('Document export exceeds its size limit; no package prepared.')
        parts[name] = content
    metadata = {'format': FORMAT_VERSION, 'synthetic_only': True, 'dealership_id': dealership_id,
        'exported_by_user_id': actor.pk, 'capture_started_at': started.isoformat(),
        'consistency': 'Multiple queries and file reads; not a guaranteed point-in-time snapshot.',
        'scope': 'Documents-owned records, snapshots, histories and artifact bytes only; not a complete backup.',
        'deal_files': [], 'deal_file_events': [_metadata(e) for e in file_events],
        'packets': [], 'packet_export_events': [_metadata(e) for e in packet_events],
        'vehicle_invoices': [], 'vehicle_invoice_events': [_metadata(e) for e in invoice_events],
        'vehicle_acquisition_files': [], 'vehicle_acquisition_file_events': [_metadata(e) for e in acquisition_events]}
    for record in files:
        name = f'deal-files/{record.pk}.pdf'
        add(name, _artifact(record, 'deal-files'))
        metadata['deal_files'].append({**_metadata(record), 'artifact': name})
    for record in invoices:
        name = f'vehicle-invoices/{record.pk}.pdf'
        add(name, _artifact(record, 'vehicle-invoices'))
        metadata['vehicle_invoices'].append({**_metadata(record), 'artifact': name})
    for record in acquisition_files:
        name = f'vehicle-acquisition/{record.pk}.pdf'
        add(name, _artifact(record, 'vehicle-acquisition'))
        metadata['vehicle_acquisition_files'].append({**_metadata(record), 'artifact': name})
    for packet in packets:
        html = packet.html.encode('utf-8')
        if hashlib.sha256(html).hexdigest() != packet.artifact_sha256 or source_digest(packet.snapshot) != packet.source_sha256:
            raise DocumentsExportError('A saved packet failed its integrity check; no package prepared.')
        name = f'packets/{packet.pk}.html'
        add(name, html)
        metadata['packets'].append({**_metadata(packet, omit=('html',)), 'artifact': name})
    metadata['capture_finished_at'] = timezone.now().isoformat()
    try:
        serialized = (json.dumps(metadata, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
    except (ValueError, TypeError) as error:
        raise DocumentsExportError('Document metadata is not valid JSON; no package prepared.') from error
    add('metadata.json', serialized)
    manifest = {'format': FORMAT_VERSION, 'synthetic_only': True, 'dealership_id': dealership_id,
                'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in parts.items()}}
    manifest_bytes = (json.dumps(manifest, sort_keys=True) + '\n').encode('utf-8')
    add('manifest.json', manifest_bytes)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            archive.writestr(info, content)
    return buffer.getvalue()

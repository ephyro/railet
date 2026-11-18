# SPDX-License-Identifier: MPL-2.0
"""Internal synthetic inventory export; not a complete backup or restore format.

This service does not itself write files, encrypt data, or audit delivery.
Queries run in one transaction after locking the dealership and owner membership
rows, but do not establish a repeatable-read snapshot across concurrent
unserialized writes on PostgreSQL READ COMMITTED (or against concurrent
filesystem changes). Actor IDs are provenance references, not exported user
records; free-text values are unredacted.
"""
from decimal import Decimal
import hashlib
import posixpath
from io import BytesIO
from pathlib import Path, PurePosixPath
import warnings
from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousFileOperation
from django.db import models, transaction
from django.utils import timezone
from core.models import AuditEvent, Dealership, Membership
from .models import (
    ReconTask,
    Vehicle,
    VehicleCostEntry,
    VehiclePhoto,
    VehicleVendor,
    VehicleVendorEvent,
)
from .photos import MAX_BYTES as MAX_PHOTO_BYTES, MAX_PIXELS as MAX_PHOTO_PIXELS

FORMAT_VERSION = 'railet-synthetic-inventory-v1'
MAX_VEHICLES = 10000
MAX_PHOTOS = 100000
MAX_VENDORS = 10000
MAX_VENDOR_EVENTS = 100000
MAX_TASKS = 100000
MAX_COSTS = 100000
MAX_AUDIT_EVENTS = 100000
MAX_TOTAL_PHOTO_BYTES = 64 * 1024 * 1024


class InventoryExportError(Exception):
    """Base error for aborted inventory exports; never returns partial data."""


class InventoryExportTooLarge(InventoryExportError):
    """Refuse partial exports when record or byte limits are exceeded."""


class InventoryPhotoArtifactError(InventoryExportError):
    """Abort export when a retained photo file is missing, out of scope, or corrupt."""


def _bounded(query, maximum):
    records = list(query[:maximum + 1])
    if len(records) > maximum:
        raise InventoryExportTooLarge('Inventory export exceeds its limit; no partial data returned.')
    return records


def _iso(value):
    return value.isoformat() if value is not None else None


def _money_str(value):
    return format(value, '.2f') if value is not None else None


def _read_verified_jpeg(field, *, dealership_id, label):
    name = getattr(field, 'name', '') or ''
    if (not name or '\\' in name or str(PurePosixPath(name)) != name
            or not name.startswith('vehicles/') or '..' in Path(name).parts):
        raise InventoryPhotoArtifactError(f'Photo {label} path is outside the vehicles storage scope.')
    if VehiclePhoto.objects.exclude(vehicle__dealership_id=dealership_id).filter(
        models.Q(image=name) | models.Q(thumbnail=name)
    ).exists():
        raise InventoryPhotoArtifactError(f'Photo {label} path is referenced by another dealership.')
    storage = field.storage
    try:
        raw_root = Path(storage.location)
        raw_path = Path(storage.path(name))
        if raw_root.is_symlink() or raw_path.is_symlink():
            raise InventoryPhotoArtifactError(f'Photo {label} path must not use symlinks.')
        for parent in raw_path.parents:
            if parent.is_symlink():
                raise InventoryPhotoArtifactError(f'Photo {label} directory path must not use symlinks.')
            if parent == raw_root:
                break
        root = raw_root.resolve()
        resolved = raw_path.resolve()
    except (SuspiciousFileOperation, ValueError, OSError) as error:
        raise InventoryPhotoArtifactError(f'Photo {label} storage path is invalid.') from error
    if not resolved.is_relative_to(root):
        raise InventoryPhotoArtifactError(f'Photo {label} path escapes private media root.')
    try:
        with storage.open(name, 'rb') as handle:
            data = handle.read(MAX_PHOTO_BYTES + 1)
    except (FileNotFoundError, SuspiciousFileOperation, OSError) as error:
        raise InventoryPhotoArtifactError(f'Photo {label} file is unavailable.') from error
    if not data:
        raise InventoryPhotoArtifactError(f'Photo {label} file is empty.')
    if len(data) > MAX_PHOTO_BYTES:
        raise InventoryExportTooLarge(f'Photo {label} exceeds the per-file size limit.')
    if not data.startswith(b'\xff\xd8'):
        raise InventoryPhotoArtifactError(f'Photo {label} is not a JPEG byte stream.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            stream = BytesIO(data)
            with Image.open(stream, formats=['JPEG']) as image:
                if image.width * image.height > MAX_PHOTO_PIXELS:
                    raise InventoryPhotoArtifactError(f'Photo {label} exceeds pixel bounds.')
                if getattr(image, 'n_frames', 1) != 1:
                    raise InventoryPhotoArtifactError(f'Photo {label} is not a single-frame JPEG.')
                image.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise InventoryPhotoArtifactError(f'Photo {label} failed JPEG integrity verification.') from error
    return data, hashlib.sha256(data).hexdigest()


def authorize_inventory_export(*, dealership_id, actor):
    """Call inside an atomic block; lock dealership and recheck active owner membership."""
    if not (getattr(settings, 'DEBUG', False) and getattr(settings, 'RECON_DEMO_ENABLED', False)):
        raise PermissionDenied('Synthetic inventory export is disabled.')
    if not getattr(actor, 'is_authenticated', False) or not getattr(actor, 'pk', None):
        raise PermissionDenied
    if not Dealership.objects.select_for_update().filter(pk=dealership_id).exists():
        raise PermissionDenied
    membership = Membership.objects.select_for_update().filter(
        user_id=actor.pk, user__is_active=True, dealership_id=dealership_id, role=Membership.Role.OWNER,
    ).first()
    if membership is None:
        raise PermissionDenied
    return membership


@transaction.atomic
def export_inventory(*, dealership_id, actor):
    """Return JSON-compatible inventory module records and verified photo bytes for an active owner.

    Includes vehicles, active and archived photo metadata with verified JPEG
    original and thumbnail bytes (`photo_artifacts`), vendors, vendor change
    events, reconditioning tasks, itemized cost/reversal entries, and vehicle
    audit events. Aborts the entire export if any referenced photo is missing,
    corrupt, oversized, or outside `vehicles/`. Does not include cross-module
    deals, customers, documents/invoices, or database/media restore tooling.
    """
    authorize_inventory_export(dealership_id=dealership_id, actor=actor)
    started = timezone.now()

    vehicles = _bounded(
        Vehicle.objects.filter(dealership_id=dealership_id).order_by('pk').values(
            'id', 'dealership_id', 'stock_number', 'vin', 'year', 'make', 'model',
            'title_brand', 'title_received', 'odometer_reading', 'odometer_unit',
            'odometer_status', 'status', 'acquired_on', 'sold_on', 'acquisition_cost',
            'recon_cost', 'asking_price', 'notes', 'updated_at', 'revision',
        ),
        MAX_VEHICLES,
    )
    photo_models = _bounded(
        VehiclePhoto.objects.filter(vehicle__dealership_id=dealership_id).order_by('pk'),
        MAX_PHOTOS,
    )
    # Normalize foreign references as well: aliases in either dealership's
    # stored name can point at the same private file.
    local_photo_names = {posixpath.normpath(field.name) for photo in photo_models
                         for field in (photo.image, photo.thumbnail) if field.name}
    if local_photo_names:
        for image_name, thumb_name in VehiclePhoto.objects.exclude(vehicle__dealership_id=dealership_id).values_list(
                'image', 'thumbnail').iterator(chunk_size=1000):
            if any(name and posixpath.normpath(name) in local_photo_names for name in (image_name, thumb_name)):
                raise InventoryPhotoArtifactError('A photo storage reference is shared across dealerships.')
    vendors = _bounded(
        VehicleVendor.objects.filter(dealership_id=dealership_id).order_by('pk').values(
            'id', 'dealership_id', 'name', 'normalized_name', 'contact_name', 'phone',
            'email', 'address', 'notes', 'revision', 'created_by_id', 'created_at', 'updated_at',
        ),
        MAX_VENDORS,
    )
    vendor_events = _bounded(
        VehicleVendorEvent.objects.filter(vendor__dealership_id=dealership_id).order_by('pk').values(
            'id', 'vendor_id', 'actor_id', 'action', 'changes', 'created_at',
        ),
        MAX_VENDOR_EVENTS,
    )
    tasks = _bounded(
        ReconTask.objects.filter(vehicle__dealership_id=dealership_id).order_by('pk').values(
            'id', 'vehicle_id', 'title', 'detail', 'status', 'vendor_id', 'assigned_to_id',
            'due_on', 'revision', 'creation_key', 'created_by_id', 'created_at', 'updated_at',
        ),
        MAX_TASKS,
    )
    costs = _bounded(
        VehicleCostEntry.objects.filter(vehicle__dealership_id=dealership_id).order_by('pk').values(
            'id', 'vehicle_id', 'kind', 'category', 'description', 'amount_cents',
            'debit', 'credit', 'vendor_id', 'vendor_name', 'task_id', 'reverses_id',
            'reason', 'effective_on', 'request_key', 'actor_id', 'entered_at',
        ),
        MAX_COSTS,
    )
    # Capture both sides in one query so mismatches cannot be silently filtered
    # out. Never return the cross-dealership row or its details to either owner.
    audit_events = _bounded(
        AuditEvent.objects.filter(
            models.Q(dealership_id=dealership_id) | models.Q(vehicle__dealership_id=dealership_id)
        ).order_by('pk').values(
            'id', 'dealership_id', 'vehicle_id', 'vehicle__dealership_id',
            'actor_id', 'action', 'changes', 'created_at',
        ),
        MAX_AUDIT_EVENTS,
    )
    for event in audit_events:
        if event.pop('vehicle__dealership_id') != event['dealership_id']:
            raise InventoryExportError('An inventory audit reference is inconsistent; no data returned.')

    for record in vehicles:
        record['acquired_on'] = _iso(record['acquired_on'])
        record['sold_on'] = _iso(record['sold_on'])
        record['updated_at'] = _iso(record['updated_at'])
        record['acquisition_cost'] = _money_str(record['acquisition_cost'])
        record['recon_cost'] = _money_str(record['recon_cost'])
        record['asking_price'] = _money_str(record['asking_price'])

    photos = []
    photo_artifacts = {}
    total_photo_bytes = 0
    for photo in photo_models:
        image_bytes, image_sha256 = _read_verified_jpeg(photo.image, dealership_id=dealership_id, label=f'#{photo.pk} image')
        thumb_bytes, thumb_sha256 = _read_verified_jpeg(photo.thumbnail, dealership_id=dealership_id, label=f'#{photo.pk} thumbnail')
        total_photo_bytes += len(image_bytes) + len(thumb_bytes)
        if total_photo_bytes > MAX_TOTAL_PHOTO_BYTES:
            raise InventoryExportTooLarge('Total vehicle photo bytes exceed the export size limit; no partial data returned.')
        image_artifact_id = f'photos/photo-{photo.pk}-image.jpg'
        thumb_artifact_id = f'photos/photo-{photo.pk}-thumbnail.jpg'
        photo_artifacts[image_artifact_id] = image_bytes
        photo_artifacts[thumb_artifact_id] = thumb_bytes
        photos.append({
            'id': photo.pk,
            'vehicle_id': photo.vehicle_id,
            'image_path': photo.image.name,
            'image_artifact_id': image_artifact_id,
            'image_bytes': len(image_bytes),
            'image_sha256': image_sha256,
            'thumbnail_path': photo.thumbnail.name,
            'thumbnail_artifact_id': thumb_artifact_id,
            'thumbnail_bytes': len(thumb_bytes),
            'thumbnail_sha256': thumb_sha256,
            'digest_basis': 'calculated_at_export_not_stored_at_upload',
            'is_primary': photo.is_primary,
            'created_by_id': photo.created_by_id,
            'created_at': _iso(photo.created_at),
            'archived_at': _iso(photo.archived_at),
        })

    for record in vendors:
        record['created_at'] = _iso(record['created_at'])
        record['updated_at'] = _iso(record['updated_at'])

    for record in vendor_events:
        record['created_at'] = _iso(record['created_at'])

    for record in tasks:
        record['due_on'] = _iso(record['due_on'])
        record['created_at'] = _iso(record['created_at'])
        record['updated_at'] = _iso(record['updated_at'])
        record['creation_key'] = str(record['creation_key'])

    for record in costs:
        record['amount_usd'] = format(Decimal(record['amount_cents']) / 100, '.2f')
        record['effective_on'] = _iso(record['effective_on'])
        record['entered_at'] = _iso(record['entered_at'])
        record['request_key'] = str(record['request_key'])

    for record in audit_events:
        record['created_at'] = _iso(record['created_at'])

    return {
        'format': FORMAT_VERSION,
        'synthetic_only': True,
        'dealership_id': dealership_id,
        'exported_by_user_id': actor.pk,
        'capture_started_at': _iso(started),
        'capture_finished_at': _iso(timezone.now()),
        'consistency': (
            'Multiple database queries and private media reads in one transaction; '
            'not guaranteed to represent a single point in time across concurrent unserialized writes.'
        ),
        'scope': (
            'Inventory module records and JPEG-checked private vehicle photo bytes (active and archived '
            'original and thumbnail files) only; VehiclePhoto does not store upload-time SHA-256 digests, '
            'so photo SHA-256 values are calculated at export and do not prove bytes are unchanged since upload. '
            'Other modules and vehicle invoice PDFs are excluded. Not a complete dealership backup or restore bundle.'
        ),
        'vehicles': vehicles,
        'photos': photos,
        'photo_artifacts': photo_artifacts,
        'vendors': vendors,
        'vendor_events': vendor_events,
        'tasks': tasks,
        'cost_entries': costs,
        'audit_events': audit_events,
    }

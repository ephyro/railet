# SPDX-License-Identifier: MPL-2.0
from io import BytesIO
import logging
from uuid import uuid4
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from core.models import AuditEvent, Dealership, Membership
from .models import Vehicle, VehiclePhoto

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_PHOTOS = 24
logger = logging.getLogger(__name__)


def normalize_photo(upload):
    if upload.size > MAX_BYTES:
        raise ValidationError("Each photo must be 8 MB or smaller.")
    data = upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValidationError("Each photo must be 8 MB or smaller.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            stream = BytesIO(data)
            with Image.open(stream, formats=["JPEG", "PNG", "WEBP"]) as image:
                if image.width * image.height > MAX_PIXELS:
                    raise ValidationError("This photo is too large. Resize it below 40 megapixels.")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValidationError("Choose a still photo rather than an animation.")
                image.verify()
            stream.seek(0)
            with Image.open(stream, formats=["JPEG", "PNG", "WEBP"]) as image:
                image.load()
                oriented = ImageOps.exif_transpose(image)
                try:
                    oriented.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
                    rgba = oriented.convert("RGBA")
                    clean = Image.new("RGB", rgba.size, "white")
                    clean.paste(rgba, mask=rgba.getchannel("A"))
                    rgba.close()
                finally:
                    oriented.close()
            try:
                full = BytesIO()
                clean.save(full, format="JPEG", quality=88, exif=b"", icc_profile=None)
                thumbnail = ImageOps.fit(clean, (320, 220), method=Image.Resampling.LANCZOS)
                try:
                    small = BytesIO()
                    thumbnail.save(small, format="JPEG", quality=82, exif=b"", icc_profile=None)
                finally:
                    thumbnail.close()
                return full.getvalue(), small.getvalue()
            finally:
                clean.close()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValidationError("This file could not be read as a photo. Choose a valid JPEG, PNG, or WebP image.") from error


def _require_locked_editor(actor, dealership_id):
    if not getattr(actor, 'is_authenticated', False) or not getattr(actor, 'pk', None):
        raise PermissionDenied
    if not Membership.objects.select_for_update().filter(
        user_id=actor.pk, user__is_active=True, dealership_id=dealership_id,
        role__in=[Membership.Role.OWNER, Membership.Role.STAFF],
    ).exists():
        raise PermissionDenied


def add_photos(vehicle, prepared, *, actor):
    written = []
    try:
        # An outer rollback would otherwise leave successfully written files orphaned.
        with transaction.atomic(durable=True):
            dealership_id = vehicle.dealership_id
            Dealership.objects.select_for_update().get(pk=dealership_id)
            vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk, dealership_id=dealership_id)
            _require_locked_editor(actor, dealership_id)
            active = vehicle.photos.filter(archived_at__isnull=True)
            count = active.count()
            if count + len(prepared) > MAX_PHOTOS:
                raise ValidationError(f"Keep up to {MAX_PHOTOS} visible photos per vehicle. Hide an old photo first.")
            photos = []
            for index, (full, small) in enumerate(prepared):
                photo = VehiclePhoto(vehicle=vehicle, created_by=actor, is_primary=count == 0 and index == 0)
                token = uuid4().hex
                for field, content, suffix in ((photo.image, full, ".jpg"), (photo.thumbnail, small, "-thumb.jpg")):
                    field.save(token + suffix, ContentFile(content), save=False)
                    written.append((field.storage, field.name))
                photo.save()
                photos.append(photo)
            AuditEvent.objects.create(dealership=vehicle.dealership, actor=actor, vehicle=vehicle, action="added photos to", changes={"photos": {"before": "", "after": [photo.pk for photo in photos]}})
            return photos
    except BaseException:
        cleanup_failures = 0
        for storage, name in written:
            try:
                storage.delete(name)
            except BaseException:
                cleanup_failures += 1
        if cleanup_failures:
            try:
                logger.error("Failed to clean up %d newly written vehicle photo blobs after an upload failure.", cleanup_failures)
            except BaseException:
                pass
        raise


@transaction.atomic
def change_photo(photo, action, *, actor):
    dealership_id = Vehicle.objects.values_list('dealership_id', flat=True).get(pk=photo.vehicle_id)
    Dealership.objects.select_for_update().get(pk=dealership_id)
    vehicle = Vehicle.objects.select_for_update().get(pk=photo.vehicle_id, dealership_id=dealership_id)
    _require_locked_editor(actor, dealership_id)
    photo = vehicle.photos.select_for_update().get(pk=photo.pk)
    if action == "cover" and photo.archived_at is None:
        if photo.is_primary:
            return
        vehicle.photos.filter(is_primary=True).update(is_primary=False)
        photo.is_primary = True
    elif action == "hide" and photo.archived_at is None:
        photo.archived_at = timezone.now()
        photo.is_primary = False
    elif action == "restore" and photo.archived_at is not None:
        active = vehicle.photos.filter(archived_at__isnull=True)
        if active.count() >= MAX_PHOTOS:
            raise ValidationError(f"Keep up to {MAX_PHOTOS} visible photos. Hide another photo first.")
        photo.archived_at = None
        photo.is_primary = not active.exists()
    else:
        raise ValidationError("Choose an available photo action.")
    photo.save(update_fields=["archived_at", "is_primary"])
    if not vehicle.photos.filter(is_primary=True, archived_at__isnull=True).exists():
        next_photo = vehicle.photos.filter(archived_at__isnull=True).first()
        if next_photo:
            next_photo.is_primary = True
            next_photo.save(update_fields=["is_primary"])
    AuditEvent.objects.create(dealership=vehicle.dealership, actor=actor, vehicle=vehicle, action="changed photos on", changes={"photo": {"before": photo.pk, "after": action}})

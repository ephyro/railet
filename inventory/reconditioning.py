# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.conf import settings
from django.db import transaction
from django.db.models import BigIntegerField, Case, F, OuterRef, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from core.models import AuditEvent, Dealership, Membership
from .models import Vehicle, VehicleVendor, VehicleVendorEvent, ReconTask, VehicleCostEntry


def with_cost_totals(queryset):
    net = VehicleCostEntry.objects.filter(vehicle_id=OuterRef('pk')).order_by().values('vehicle_id').annotate(
        net=Sum(Case(When(kind='cost', then=F('amount_cents')), default=-F('amount_cents'), output_field=BigIntegerField()))
    ).values('net')
    return queryset.annotate(registered_cost_cents=Coalesce(Subquery(net, output_field=BigIntegerField()), Value(0, output_field=BigIntegerField())))


def _lock(*, vehicle_id, dealership, actor):
    if not getattr(settings, 'RECON_DEMO_ENABLED', False):
        raise PermissionDenied('Vehicle work and cost rehearsal is disabled.')
    Dealership.objects.select_for_update().get(pk=dealership.pk)
    if not Membership.objects.filter(user=actor, dealership=dealership, role__in=['owner', 'staff']).exists():
        raise PermissionDenied('Inventory changes require an owner or inventory staff role.')
    try:
        return Vehicle.objects.select_for_update().get(pk=vehicle_id, dealership=dealership)
    except Vehicle.DoesNotExist:
        raise ValidationError('Choose a vehicle from this dealership.')


def _vendor(dealership, actor, vendor, new_vendor):
    if vendor and new_vendor:
        raise ValidationError('Choose a vendor or enter a new one, not both.')
    if vendor:
        if vendor.dealership_id != dealership.pk:
            raise ValidationError('Choose a vendor from this dealership.')
        return vendor
    if new_vendor:
        name = ' '.join(new_vendor.split())
        normalized = name.casefold()
        if not name or len(normalized) > 120 or len(name) > 120:
            raise ValidationError('Use a vendor name of up to 120 characters.')
        vendor, created = VehicleVendor.objects.get_or_create(dealership=dealership, normalized_name=normalized, defaults={'name': name, 'created_by': actor})
        if created:
            VehicleVendorEvent.objects.create(vendor=vendor, actor=actor, action='created', changes={
                'name': {'before': None, 'after': vendor.name},
                'revision': vendor.revision,
            })
    return vendor or None


@transaction.atomic
def save_vendor(*, dealership, actor, data, vendor_id=None):
    if not getattr(settings, 'RECON_DEMO_ENABLED', False):
        raise PermissionDenied('Vehicle work and cost rehearsal is disabled.')
    Dealership.objects.select_for_update().get(pk=dealership.pk)
    if not Membership.objects.filter(user=actor, dealership=dealership, role__in=['owner', 'staff']).exists():
        raise PermissionDenied('Inventory changes require an owner or inventory staff role.')
    name = ' '.join(data.get('name', '').split())
    normalized = name.casefold()
    if not name or len(normalized) > 120 or len(name) > 120:
        raise ValidationError({'name': 'Use a vendor name of up to 120 characters.'})
    fields = ('contact_name', 'phone', 'email', 'address', 'notes')
    cleaned = {key: (data.get(key) or '').strip() for key in fields}
    if vendor_id is None:
        existing = VehicleVendor.objects.filter(dealership=dealership, normalized_name=normalized).first()
        if existing:
            same = existing.created_by_id == actor.pk and existing.name == name and all(getattr(existing, key) == cleaned[key] for key in fields)
            if same:
                return existing
            raise ValidationError({'name': 'A vendor with this name already exists. Open that vendor to update its contact details.'})
        vendor = VehicleVendor(dealership=dealership, name=name, normalized_name=normalized, created_by=actor, **cleaned)
        vendor.full_clean()
        vendor.save()
        VehicleVendorEvent.objects.create(vendor=vendor, actor=actor, action='created', changes={
            'name': {'before': None, 'after': vendor.name},
            **{key: {'before': None, 'after': cleaned[key]} for key in fields if cleaned[key]},
            'revision': vendor.revision,
        })
        return vendor

    vendor = VehicleVendor.objects.select_for_update().get(pk=vendor_id, dealership=dealership)
    if data.get('revision') != vendor.revision:
        raise ValidationError('This vendor changed while you were editing. Your entries are preserved; compare with the latest vendor record before saving again.')
    if VehicleVendor.objects.filter(dealership=dealership, normalized_name=normalized).exclude(pk=vendor.pk).exists():
        raise ValidationError({'name': 'Another vendor in this dealership already uses this name.'})
    before = {'name': vendor.name, **{key: getattr(vendor, key) for key in fields}}
    after = {'name': name, **cleaned}
    if before == after:
        return vendor
    vendor.name = name
    vendor.normalized_name = normalized
    for key in fields:
        setattr(vendor, key, cleaned[key])
    vendor.revision += 1
    vendor.full_clean()
    vendor.save(update_fields=['name', 'normalized_name', *fields, 'revision', 'updated_at'])
    changes = {key: {'before': before[key], 'after': after[key]} for key in after if before[key] != after[key]}
    changes['revision'] = vendor.revision
    VehicleVendorEvent.objects.create(vendor=vendor, actor=actor, action='updated', changes=changes)
    return vendor


def _same_vendor(entry, data):
    vendor = data.get('vendor')
    new = ' '.join(data.get('new_vendor', '').split()).casefold()
    if vendor and new:
        return False
    if vendor:
        return entry.vendor_id == vendor.pk
    if new:
        return bool(entry.vendor_id) and entry.vendor.normalized_name == new
    return entry.vendor_id is None


def _assignee(dealership, assignee):
    if assignee is None:
        return None
    if not Membership.objects.filter(user=assignee, user__is_active=True, dealership=dealership, role__in=['owner', 'staff']).exists():
        raise ValidationError('Choose a current staff member from this dealership.')
    return assignee


def _audit(vehicle, actor, action, payload, before=None):
    before = before or {}
    AuditEvent.objects.create(dealership_id=vehicle.dealership_id, vehicle=vehicle, actor=actor, action=action,
                              changes={key: {'before': before.get(key), 'after': value} for key, value in payload.items()})


@transaction.atomic
def add_task(*, vehicle_id, dealership, actor, data):
    vehicle = _lock(vehicle_id=vehicle_id, dealership=dealership, actor=actor)
    detail = data.get('detail', '')
    due_on = data.get('due_on')
    assignee = _assignee(dealership, data.get('assigned_to'))
    old = ReconTask.objects.filter(vehicle=vehicle, creation_key=data['request_key']).first()
    if old:
        if (
            old.created_by_id != actor.pk
            or old.title != data['title']
            or old.detail != detail
            or old.assigned_to_id != (assignee.pk if assignee else None)
            or old.due_on != due_on
            or not _same_vendor(old, data)
        ):
            raise ValidationError('This save key has already been used.')
        return old
    vendor = _vendor(dealership, actor, data.get('vendor'), data.get('new_vendor', ''))
    task = ReconTask(vehicle=vehicle, title=data['title'], detail=detail, vendor=vendor,
                     assigned_to=assignee, due_on=due_on, creation_key=data['request_key'], created_by=actor)
    task.full_clean(); task.save()
    _audit(vehicle, actor, 'recon_task_added', {
        'task_id': task.pk, 'title': task.title, 'detail': task.detail,
        'vendor_id': vendor.pk if vendor else None,
        'assigned_to_id': assignee.pk if assignee else None,
        'due_on': due_on.isoformat() if due_on else None,
    })
    return task


@transaction.atomic
def edit_task(*, vehicle_id, dealership, actor, task_id, data):
    vehicle = _lock(vehicle_id=vehicle_id, dealership=dealership, actor=actor)
    task = ReconTask.objects.select_for_update().get(pk=task_id, vehicle=vehicle)
    if data['revision'] != task.revision:
        raise ValidationError('This task changed while you were editing. Your entries are preserved; reload the work list before saving again.')
    status = data.get('status', task.status)
    if status not in ReconTask.Status.values:
        raise ValidationError('Choose To do, In progress, or Done.')
    assignee = _assignee(dealership, data.get('assigned_to'))
    vendor = _vendor(dealership, actor, data.get('vendor'), data.get('new_vendor', ''))
    detail = data.get('detail', '')
    due_on = data.get('due_on')
    before = {
        'title': task.title,
        'detail': task.detail,
        'status': task.status,
        'vendor_id': task.vendor_id,
        'assigned_to_id': task.assigned_to_id,
        'due_on': task.due_on.isoformat() if task.due_on else None,
    }
    after = {
        'title': data['title'],
        'detail': detail,
        'status': status,
        'vendor_id': vendor.pk if vendor else None,
        'assigned_to_id': assignee.pk if assignee else None,
        'due_on': due_on.isoformat() if due_on else None,
    }
    if before == after:
        return task
    task.title = data['title']
    task.detail = detail
    task.status = status
    task.vendor = vendor
    task.assigned_to = assignee
    task.due_on = due_on
    task.revision += 1
    task.full_clean()
    task.save(update_fields=['title', 'detail', 'status', 'vendor', 'assigned_to', 'due_on', 'revision', 'updated_at'])
    changed = {key: after[key] for key in after if before[key] != after[key]}
    changed['task_id'] = task.pk
    changed['revision'] = task.revision
    _audit(vehicle, actor, 'recon_task_updated', changed, before={**before, 'task_id': task.pk, 'revision': task.revision - 1})
    return task


@transaction.atomic
def change_task(*, vehicle_id, dealership, actor, task_id, revision, status):
    vehicle = _lock(vehicle_id=vehicle_id, dealership=dealership, actor=actor)
    task = ReconTask.objects.get(pk=task_id, vehicle=vehicle)
    if task.revision != revision:
        raise ValidationError('This task changed. Reload the work list before updating it.')
    if status not in ReconTask.Status.values:
        raise ValidationError('Choose To do, In progress, or Done.')
    if task.status == status:
        return task
    before = task.status
    task.status = status; task.revision += 1
    task.save(update_fields=['status', 'revision', 'updated_at'])
    _audit(vehicle, actor, 'recon_task_changed', {'task_id': task.pk, 'status_from': before, 'status_to': status, 'revision': task.revision})
    return task


@transaction.atomic
def add_cost(*, vehicle_id, dealership, actor, data):
    vehicle = _lock(vehicle_id=vehicle_id, dealership=dealership, actor=actor)
    amount = data['amount']
    if not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0 or amount > Decimal('9999999999.99') or amount != amount.quantize(Decimal('.01')):
        raise ValidationError('Enter a positive cost with at most two decimal places.')
    if data['effective_on'] > timezone.localdate():
        raise ValidationError('Use today or an earlier date for an incurred cost.')
    old = VehicleCostEntry.objects.filter(vehicle=vehicle, request_key=data['request_key']).first()
    if old:
        if old.actor_id != actor.pk or old.kind != 'cost' or old.amount_cents != int(amount * 100) or old.description != data['description'] or old.category != data['category'] or old.effective_on != data['effective_on'] or old.task_id != getattr(data.get('task'), 'pk', None) or not _same_vendor(old, data):
            raise ValidationError('This save key belongs to a different cost. Reload before recording another.')
        return old
    task = data.get('task') or None
    if task and task.vehicle_id != vehicle.pk:
        raise ValidationError('Choose work for this vehicle.')
    vendor = _vendor(dealership, actor, data.get('vendor'), data.get('new_vendor', ''))
    entry = VehicleCostEntry(vehicle=vehicle, kind='cost', amount_cents=int(amount * 100), category=data['category'],
        description=data['description'], vendor=vendor, vendor_name=vendor.name if vendor else '', task=task,
        effective_on=data['effective_on'], request_key=data['request_key'], actor=actor)
    entry.full_clean(); entry.save()
    _audit(vehicle, actor, 'vehicle_cost_added', {'entry_id': entry.pk, 'amount': str(amount), 'category': entry.category, 'vendor': entry.vendor_name, 'effective_on': entry.effective_on.isoformat()})
    return entry


@transaction.atomic
def reverse_cost(*, vehicle_id, dealership, actor, entry_id, reason, request_key):
    vehicle = _lock(vehicle_id=vehicle_id, dealership=dealership, actor=actor)
    source = VehicleCostEntry.objects.get(pk=entry_id, vehicle=vehicle, kind='cost')
    reason = reason.strip()
    if not reason or len(reason) > 300:
        raise ValidationError('Enter a correction reason of up to 300 characters.')
    old = VehicleCostEntry.objects.filter(reverses=source).first()
    if old:
        if old.request_key == request_key and old.actor_id == actor.pk and old.reason == reason:
            return old
        raise ValidationError('This cost has already been reversed. The original and correction are retained.')
    if VehicleCostEntry.objects.filter(vehicle=vehicle, request_key=request_key).exists():
        raise ValidationError('This save key has already been used. Reload the correction page.')
    reversal = VehicleCostEntry(vehicle=vehicle, kind='reversal', category=source.category, description=source.description,
        amount_cents=source.amount_cents, debit='cost_offset', credit='vehicle_cost', vendor=source.vendor,
        vendor_name=source.vendor_name, task=source.task, reverses=source, reason=reason, effective_on=timezone.localdate(),
        request_key=request_key, actor=actor)
    reversal.full_clean(); reversal.save()
    _audit(vehicle, actor, 'vehicle_cost_reversed', {'entry_id': reversal.pk, 'reverses_id': source.pk, 'amount': str(source.amount), 'reason': reason})
    return reversal

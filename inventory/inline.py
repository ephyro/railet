# SPDX-License-Identifier: MPL-2.0
"""Inventory-owned inline entry for a draft; uses ordinary identity/VIN controls."""
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from core.models import AuditEvent,Dealership,Membership
from .forms import VehicleForm
from .models import Vehicle
from .vin_matching import matching_vehicles

class InlineVehicleForm(VehicleForm):
    def __init__(self,*args,dealership,**kwargs):
        kwargs.setdefault('instance',Vehicle(dealership=dealership))
        if args and args[0] is not None:
            data=args[0].copy();prefix=kwargs.get('prefix','')
            for name in self.Meta.fields:
                default=getattr(kwargs['instance'],name)
                key=f'{prefix}-{name}' if prefix else name
                if name not in ('stock_number','year','make','model'):data.setdefault(key,'' if default is None else default)
            args=(data,*args[1:])
        super().__init__(*args,dealership=dealership,**kwargs)
    def clean(self):
        data=super().clean()
        if data.get('status')=='sold':self.add_error('status','Add this vehicle to active inventory before starting its sale.')
        if data.get('stock_number') and Vehicle.objects.filter(dealership=self.dealership,stock_number=data['stock_number']).exists():
            self.add_error('stock_number','This stock number already exists. Choose the inventory vehicle or use a different stock number.')
        return data

@transaction.atomic
def create_inline_vehicle(form,*,dealership,actor):
    if not Membership.objects.filter(dealership=dealership,user=actor,role__in=['owner','staff']).exists():raise PermissionDenied
    if form.instance.pk or form.instance.dealership_id!=dealership.pk:raise ValidationError('Use a new vehicle from this dealership.')
    Dealership.objects.select_for_update().get(pk=dealership.pk)
    matches=set(matching_vehicles(dealership=dealership,vin=form.cleaned_data.get('vin','')).values_list('pk',flat=True)) if form.cleaned_data.get('vin') else set()
    reviewed={v.pk for v in form.duplicate_matches}
    if matches!=reviewed:raise ValidationError('Inventory changed during entry. Review matching VINs again before saving.')
    form.instance.full_clean();vehicle=form.save()
    changes={name:{'before':None,'after':str(getattr(vehicle,name))} for name in form.Meta.fields}
    if form.duplicate_review_metadata:changes['duplicate_vin_review']={'before':None,'after':form.duplicate_review_metadata}
    AuditEvent.objects.create(dealership=dealership,actor=actor,vehicle=vehicle,action='created',changes=changes)
    return vehicle

# SPDX-License-Identifier: MPL-2.0
"""Inventory-owned creation interface; callers supply reviewed identity, not deal models."""
from django.core.exceptions import ValidationError
from django.db import transaction
from core.models import AuditEvent, Dealership
from .models import Vehicle
from .identity import ODOMETER_FIELDS

IDENTITY_FIELDS = ("vin", "year", "make", "model", "title_brand", *ODOMETER_FIELDS)


@transaction.atomic
def create_trade_vehicle(*, dealership, actor, identity, stock_number, acquisition_cost, title_received, source_trade_id):
    # Serialize intake duplicate checks within a dealership; stock uniqueness is also a DB constraint.
    Dealership.objects.select_for_update().get(pk=dealership.pk)
    if identity["vin"] and Vehicle.objects.filter(dealership=dealership, vin__iexact=identity["vin"]).exists():
        raise ValidationError("A vehicle with this VIN is already in this dealership's inventory. Review that vehicle before creating another record.")
    vehicle = Vehicle(dealership=dealership, stock_number=stock_number,
                      acquisition_cost=acquisition_cost, title_received=title_received,
                      status=Vehicle.Status.ACQUIRED, **{name: identity[name] for name in IDENTITY_FIELDS})
    vehicle.full_clean()
    vehicle.save()
    AuditEvent.objects.create(dealership=dealership, actor=actor, vehicle=vehicle, action="created",
                              changes={**{name: {"before": None, "after": str(getattr(vehicle, name))} for name in (*IDENTITY_FIELDS, "stock_number", "status", "acquisition_cost", "title_received")},
                                       "source_trade_id": {"before": None, "after": source_trade_id}})
    return vehicle

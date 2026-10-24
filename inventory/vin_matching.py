# SPDX-License-Identifier: MPL-2.0
"""Same-dealership VIN matching for explicit inventory duplicate review."""
from django.db.models import CharField
from django.db.models.functions import Upper, Trim

from .models import Vehicle


def normalize_vin(value):
    """Normalize the user-entered or saved VIN representation for comparison."""
    return (value or "").strip().upper()


def matching_vehicles(*, dealership, vin, exclude_vehicle_id=None):
    """Return same-dealership records with this normalized VIN, including sold stock."""
    normalized = normalize_vin(vin)
    if not normalized:
        return Vehicle.objects.none()

    matches = (
        Vehicle.objects.filter(dealership_id=dealership.pk)
        .annotate(_normalized_vin=Upper(Trim("vin"), output_field=CharField()))
        .filter(_normalized_vin=normalized)
    )
    if exclude_vehicle_id is not None:
        matches = matches.exclude(pk=exclude_vehicle_id)
    return matches.order_by("stock_number", "pk")

# SPDX-License-Identifier: MPL-2.0
"""Same-dealership VIN matching for explicit inventory duplicate review."""
from django.db.models import CharField, F, Func, Value
from django.db.models.functions import Upper

from .models import Vehicle

# Python str.strip() whitespace, passed as the trim character set to both
# SQLite and PostgreSQL. Internal whitespace is deliberately left untouched.
_TRIM_CHARS = ''.join(chr(code) for code in (
    *range(0x09, 0x0e), *range(0x1c, 0x21), 0x85, 0xa0, 0x1680,
    *range(0x2000, 0x200b), 0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
))


def normalized_vin_expression():
    """Database comparison for stored VINs, shared by matching and reports."""
    right = Func(F('vin'), Value(_TRIM_CHARS), function='RTRIM', output_field=CharField())
    return Upper(Func(right, Value(_TRIM_CHARS), function='LTRIM', output_field=CharField()))


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
        .annotate(_normalized_vin=normalized_vin_expression())
        .filter(_normalized_vin=normalized)
    )
    if exclude_vehicle_id is not None:
        matches = matches.exclude(pk=exclude_vehicle_id)
    return matches.order_by("stock_number", "pk")

# SPDX-License-Identifier: MPL-2.0
from django.core.exceptions import ValidationError
from django.db import models


class OdometerUnit(models.TextChoices):
    UNKNOWN = "unknown", "Not verified"
    MILES = "miles", "Miles"
    KM = "km", "Kilometers"


class OdometerStatus(models.TextChoices):
    UNKNOWN = "unknown", "Not verified"
    ACTUAL = "actual", "Actual mileage reported"
    NOT_ACTUAL = "not_actual", "Not actual mileage reported"
    EXCEEDS = "exceeds", "Exceeds mechanical limits reported"
    EXEMPT = "exempt", "Exemption claimed — review required"


ODOMETER_FIELDS = ("odometer_reading", "odometer_unit", "odometer_status")


def validate_odometer(record):
    # These are consistency checks, not a transferor certification or exemption decision.
    if record.odometer_status in (OdometerStatus.ACTUAL, OdometerStatus.NOT_ACTUAL, OdometerStatus.EXCEEDS):
        errors = {}
        if record.odometer_reading is None:
            errors["odometer_reading"] = "Enter the reading for the reported mileage status, or choose Not verified."
        if record.odometer_unit == OdometerUnit.UNKNOWN:
            errors["odometer_unit"] = "Choose the unit for the reported reading, or leave the status Not verified."
        if errors:
            raise ValidationError(errors)

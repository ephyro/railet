# SPDX-License-Identifier: MPL-2.0
"""Explicit snapshot interface for documents and account portability."""
from .models import ADDRESS_FIELDS


def address_snapshot(customer):
    return {name:getattr(customer,name) for name in ADDRESS_FIELDS}

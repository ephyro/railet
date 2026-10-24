# SPDX-License-Identifier: MPL-2.0
from django.db.models import Q

from customers.queries import search_customers
from .models import DraftDeal


def _draft_number(query):
    digits = query.removeprefix("#")
    if digits.isascii() and digits.isdecimal() and len(digits) <= 19:
        number = int(digits)
        if 0 < number <= 9223372036854775807:
            return number
    return None


def search_drafts(dealership, query):
    drafts = DraftDeal.objects.filter(dealership=dealership)
    if not query:
        return drafts
    number = _draft_number(query)
    if query.startswith("#"):
        return drafts.filter(pk=number) if number is not None else drafts.none()

    vehicle = Q()
    for word in query.split():
        term = (
            Q(vehicle__stock_number__icontains=word)
            | Q(vehicle__vin__icontains=word)
            | Q(vehicle__make__icontains=word)
            | Q(vehicle__model__icontains=word)
        )
        if word.isascii() and word.isdecimal() and len(word) <= 4:
            term |= Q(vehicle__year=int(word))
        vehicle &= term

    customers = search_customers(dealership, query)
    match = vehicle | Q(buyer__in=customers) | Q(co_buyer__in=customers)
    if number is not None:
        match |= Q(pk=number)
    return drafts.filter(match)

# SPDX-License-Identifier: MPL-2.0
from django.db.models import Q

from .models import Customer, phone_key


def search_customers(dealership, query):
    """Return this dealership's customers matching all name/email words or a phone."""
    customers = Customer.objects.filter(dealership=dealership)
    if not query:
        return customers

    words = Q()
    for word in query.split():
        words &= (
            Q(first_name__icontains=word)
            | Q(last_name__icontains=word)
            | Q(email__icontains=word)
        )
    digits = phone_key(query)
    if digits and not any(character.isalpha() for character in query):
        words |= Q(phone_normalized__contains=digits)
    return customers.filter(words)

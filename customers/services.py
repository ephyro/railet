# SPDX-License-Identifier: MPL-2.0
from .models import CustomerEvent

def save_customer(form, *, actor, dealership):
    """Caller must validate the form and wrap this operation in a transaction."""
    customer = form.instance
    if customer.pk and customer.dealership_id != dealership.pk:
        raise ValueError("Customer dealership cannot change")
    changes = {name: str(form.cleaned_data.get(name, "")) for name in form.Meta.fields}
    customer.dealership = dealership
    if customer.pk:
        customer.revision += 1
    customer = form.save()
    CustomerEvent.objects.create(customer=customer, actor=actor, changes={"fields": changes, "revision": customer.revision})
    return customer

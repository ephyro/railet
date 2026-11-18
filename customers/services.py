# SPDX-License-Identifier: MPL-2.0
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from core.models import Dealership, Membership
from .models import Customer, CustomerEvent


def require_locked_editor(actor, dealership_id):
    if not getattr(actor, 'is_authenticated', False) or not getattr(actor, 'pk', None) or not Membership.objects.select_for_update().filter(
        user_id=actor.pk, user__is_active=True, dealership_id=dealership_id,
        role__in=[Membership.Role.OWNER, Membership.Role.STAFF],
    ).exists():
        raise PermissionDenied


@transaction.atomic
def save_customer(form, *, actor, dealership):
    """Save a validated customer form with locked authorization and audit."""
    customer = form.instance
    Dealership.objects.select_for_update().get(pk=dealership.pk)
    if form.dealership.pk != dealership.pk or (customer.dealership_id is not None and customer.dealership_id != dealership.pk):
        raise ValueError("Customer dealership cannot change")
    if customer.pk:
        current = Customer.objects.select_for_update().filter(pk=customer.pk, dealership=dealership).first()
        if current is None:
            raise ValueError("Customer dealership cannot change")
    else:
        current = None
    require_locked_editor(actor, dealership.pk)
    if current is not None and form.cleaned_data.get('revision') != current.revision:
        raise ValidationError("This customer was updated by someone else. Your entries are preserved; compare with the latest record before reloading.")
    changes = {name: str(form.cleaned_data.get(name, "")) for name in form.Meta.fields}
    customer.dealership = dealership
    if customer.pk:
        customer.revision = current.revision + 1
    customer = form.save()
    CustomerEvent.objects.create(customer=customer, actor=actor, changes={"fields": changes, "revision": customer.revision})
    return customer

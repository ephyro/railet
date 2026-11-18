# SPDX-License-Identifier: MPL-2.0
from functools import wraps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseForbidden
from .models import Dealership, Membership

def member_view(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            request.member = Membership.objects.select_related("dealership").get(user=request.user)
        except Membership.DoesNotExist:
            raise PermissionDenied("No dealership membership assigned.")
        return view(request, *args, **kwargs)
    return wrapped

def context(request, **kwargs):
    return {"member": request.member, "customer_activity_enabled": getattr(settings, "CUSTOMER_ACTIVITY_DEMO_ENABLED", False), "completion_enabled": getattr(settings, "DEMO_COMPLETION_ENABLED", False) and getattr(settings, "DEMO_PACKETS_ENABLED", False), "recon_enabled": getattr(settings, "RECON_DEMO_ENABLED", False), "deal_files_enabled": getattr(settings, "DEAL_FILES_DEMO_ENABLED", False), "demo_accounts_enabled": getattr(settings, "DEMO_LEDGER_ENABLED", False), "demo_servicing_enabled": getattr(settings,"DEMO_SERVICING_ENABLED",False) and getattr(settings,"DEMO_LEDGER_ENABLED",False), **kwargs}

def require_editor(request):
    if request.member.role not in (Membership.Role.OWNER, Membership.Role.STAFF):
        raise PermissionDenied("Your account has view-only access.")


def authorized_private_read(view):
    """Recheck and hold current member permissions while preparing private files."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        response = None
        try:
            with transaction.atomic():
                dealership_id = request.member.dealership_id
                if not Dealership.objects.select_for_update().filter(pk=dealership_id).exists():
                    raise PermissionDenied
                member = Membership.objects.select_for_update().select_related('dealership').filter(
                    user_id=request.user.pk, user__is_active=True, dealership_id=dealership_id,
                    role__in=Membership.Role.values,
                ).first()
                if member is None:
                    raise PermissionDenied
                request.member = member
                response = view(request, *args, **kwargs)
            return response
        except BaseException:
            if response is not None:
                response.close()
            raise
    return wrapped


def authorized_private_export(view):
    """Fail private export authorization with a non-cacheable response."""
    checked = authorized_private_read(view)
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        request._railet_private_response = True
        try:
            return checked(request, *args, **kwargs)
        except PermissionDenied:
            response = HttpResponseForbidden()
            response['Cache-Control'] = 'private, no-store'
            return response
    return wrapped

# SPDX-License-Identifier: MPL-2.0
from functools import wraps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from .models import Membership

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
    return {"member": request.member, "demo_accounts_enabled": getattr(settings, "DEMO_LEDGER_ENABLED", False), **kwargs}

def require_editor(request):
    if request.member.role not in (Membership.Role.OWNER, Membership.Role.STAFF):
        raise PermissionDenied("Your account has view-only access.")

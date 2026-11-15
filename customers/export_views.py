# SPDX-License-Identifier: MPL-2.0
"""Owner-only synthetic customer export review and audited download."""
import hashlib
import json
from functools import wraps
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from core.access import context, member_view
from .export import authorize_customer_export, CustomerExportTooLarge, export_customers
from .models import CustomerExportEvent

MAX_JSON_BYTES = 32 * 1024 * 1024


def private_export(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            response = view(request, *args, **kwargs)
        except PermissionDenied:
            response = HttpResponse(status=403)
        except Http404:
            response = HttpResponse(status=404)
        except DatabaseError:
            response = HttpResponse('Customer export could not be prepared. No file was returned.', status=503, content_type='text/plain')
        response['Cache-Control'] = 'private, no-store'
        response['Pragma'] = 'no-cache'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "default-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        return response
    return wrapper


@private_export
@member_view
@require_GET
@transaction.atomic
def review(request):
    authorize_customer_export(dealership_id=request.member.dealership_id, actor=request.user)
    return render(request, 'customers/export_review.html', context(request))


@private_export
@member_view
@require_POST
@transaction.atomic
def download(request):
    try:
        data = export_customers(dealership_id=request.member.dealership_id, actor=request.user)
    except CustomerExportTooLarge:
        return HttpResponse('The customer export exceeds its limit. No partial file was prepared.', status=409, content_type='text/plain')
    payload = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    if len(payload) > MAX_JSON_BYTES:
        return HttpResponse('The customer export exceeds its size limit. No partial file was prepared.', status=409, content_type='text/plain')
    CustomerExportEvent.objects.create(dealership_id=request.member.dealership_id, actor=request.user,
        format_version=data['format'], sha256=hashlib.sha256(payload).hexdigest(), byte_size=len(payload))
    response = HttpResponse(payload, content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="DEMO-customer-export.json"'
    response['Content-Length'] = str(len(payload))
    return response

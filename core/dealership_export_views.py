# SPDX-License-Identifier: MPL-2.0
import hashlib
from functools import wraps
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from core.access import context, member_view
from .dealership_export import FORMAT_VERSION, PackageError, authorize_package, build_package
from .export import FoundationExportTooLarge
from customers.export import CustomerExportTooLarge
from inventory.export import InventoryExportError
from deals.export import DealExportError
from documents.export import DocumentsExportError
from finance.export import FinanceExportError
from feedback.export import FeedbackExportTooLarge
from .models import DealershipExportEvent

SALT = 'railet.synthetic-dealership-export-review.v1'


def private(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            response = view(request, *args, **kwargs)
        except PermissionDenied:
            response = HttpResponse(status=403)
        except Http404:
            response = HttpResponse(status=404)
        except DatabaseError:
            response = HttpResponse('Export could not be prepared. No file was returned.', status=503, content_type='text/plain')
        response['Cache-Control'] = 'private, no-store'
        response['Pragma'] = 'no-cache'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "default-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        return response
    return wrapped


@private
@member_view
@require_GET
@transaction.atomic
def review(request):
    authorize_package(dealership_id=request.member.dealership_id, actor=request.user)
    token = signing.dumps({'actor': request.user.pk, 'dealership': request.member.dealership_id}, salt=SALT)
    return render(request, 'core/dealership_export.html', context(request, export_token=token))


@private
@member_view
@require_POST
@transaction.atomic
def download(request):
    authorize_package(dealership_id=request.member.dealership_id, actor=request.user)
    try:
        payload = signing.loads(request.POST.get('export_token', ''), salt=SALT, max_age=1800)
    except signing.BadSignature:
        return HttpResponse('This review expired or is invalid. Review the export again.', status=400, content_type='text/plain')
    if not isinstance(payload, dict) or (payload.get('actor'), payload.get('dealership')) != (request.user.pk, request.member.dealership_id):
        raise PermissionDenied
    try:
        package = build_package(dealership_id=request.member.dealership_id, actor=request.user)
    except (PackageError, FoundationExportTooLarge, CustomerExportTooLarge, InventoryExportError,
            DealExportError, DocumentsExportError, FinanceExportError, FeedbackExportTooLarge):
        return HttpResponse('A component could not be verified or exceeds its limit. No package was prepared.', status=409, content_type='text/plain')
    DealershipExportEvent.objects.create(dealership_id=request.member.dealership_id, actor=request.user,
        format_version=FORMAT_VERSION, sha256=hashlib.sha256(package).hexdigest(), byte_size=len(package))
    response = HttpResponse(package, content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="DEMO-dealership-data.zip"'
    response['Content-Length'] = str(len(package))
    return response

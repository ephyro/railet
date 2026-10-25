# SPDX-License-Identifier: MPL-2.0
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_GET
from core.access import member_view, context
from core.models import Dealership, Membership
from .forms import ReportForm
from .models import FeedbackReport

SALT = 'railet.feedback.preview.v1'
FIELDS = ('kind', 'area', 'subject', 'expected', 'actual')


def preview_payload(request, data):
    return {
        **{name: data[name] for name in FIELDS},
        'submission_key': str(data['submission_key']),
        'author': request.user.pk,
        'dealership': request.member.dealership_id,
        'privacy_checked': True,
    }


def private_reports(request):
    reports = FeedbackReport.objects.filter(dealership=request.member.dealership)
    if request.member.role != Membership.Role.OWNER:
        reports = reports.filter(author=request.user)
    return reports


@never_cache
@member_view
@require_http_methods(['GET', 'POST'])
def report_create(request):
    form = ReportForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        payload = preview_payload(request, form.cleaned_data)
        token = signing.dumps(payload, salt=SALT, compress=True)
        return render(request, 'feedback/preview.html', context(request, form=form, preview=payload, token=token, kind_label=dict(FeedbackReport.Kind.choices)[payload['kind']], area_label=dict(FeedbackReport.Area.choices)[payload['area']]))
    return render(request, 'feedback/form.html', context(request, form=form))


@never_cache
@member_view
@require_http_methods(['POST'])
def report_confirm(request):
    if request.FILES:
        return HttpResponseBadRequest('Attachments are not accepted.')
    try:
        payload = signing.loads(request.POST.get('preview_token', ''), salt=SALT, max_age=1800)
    except signing.BadSignature:
        return render(request, 'feedback/expired.html', context(request), status=400)
    if payload.get('author') != request.user.pk or payload.get('dealership') != request.member.dealership_id:
        raise PermissionDenied
    # Revalidate signed input rather than trusting posted report fields.
    form = ReportForm(payload)
    if not form.is_valid():
        return render(request, 'feedback/form.html', context(request, form=form), status=400)
    if request.POST.get('action') == 'edit':
        return render(request, 'feedback/form.html', context(request, form=form))
    if request.POST.get('action') != 'save':
        return HttpResponseBadRequest('Choose edit or save.')
    data = form.cleaned_data
    with transaction.atomic():
        # Serializes duplicate confirms; no report quota or external network call.
        Dealership.objects.select_for_update().get(pk=request.member.dealership_id)
        report, created = FeedbackReport.objects.get_or_create(
            dealership=request.member.dealership, author=request.user,
            submission_key=data['submission_key'],
            defaults={field: data[field] for field in FIELDS},
        )
        if not created and any(getattr(report, field) != data[field] for field in FIELDS):
            return render(request, 'feedback/conflict.html', context(request, report=report), status=409)
    return redirect('feedback_detail', pk=report.pk)


@never_cache
@member_view
@require_GET
def report_list(request):
    from django.core.paginator import Paginator
    page = Paginator(private_reports(request).select_related('author'), 25).get_page(request.GET.get('page'))
    return render(request, 'feedback/list.html', context(request, page=page))


@never_cache
@member_view
@require_GET
def report_detail(request, pk):
    report = get_object_or_404(private_reports(request).select_related('author'), pk=pk)
    return render(request, 'feedback/detail.html', context(request, report=report))

# SPDX-License-Identifier: MPL-2.0
from django import forms
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.views.decorators.http import require_GET, require_http_methods
from core.access import member_view, context, require_editor
from deals.account_context import eligible_account_drafts, account_draft_snapshot
from .models import DemoAccountContext
from .views import demo_page, scoped_book, money
from .services import reconcile, LedgerError
from .schedule_services import result_digest
from .account_services import link_draft

SALT = 'railet.synthetic-account-link.v1'


class LinkForm(forms.Form):
    deal = forms.ModelChoiceField(queryset=None, label='BHPH draft for this customer', empty_label='Choose a draft')

    def __init__(self, *args, book, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deal'].queryset = eligible_account_drafts(dealership_id=book.dealership_id, customer_id=book.customer_id)


@demo_page
@member_view
@require_GET
@transaction.atomic
def workspace(request, pk):
    book = scoped_book(request, pk, locked=True)
    account = DemoAccountContext.objects.filter(book=book).first()
    if account and result_digest(account.snapshot) != account.snapshot_sha256:
        return render(request, 'finance/account_error.html', context(request), status=409)
    totals = reconcile(dealership_id=request.member.dealership_id, book_id=book.pk)
    history = book.postings.filter(kind__in=['receipt', 'reversal']).select_related('actor', 'reversal').order_by('-entered_at', '-pk')
    page = Paginator(history, 20).get_page(request.GET.get('page'))
    rows = [{'entry': item, 'amount': money(item.amount_cents)} for item in page]
    schedules = book.schedule_illustrations.all()[:5]
    from django.conf import settings
    simulation=None;simulation_error=None
    if getattr(settings,'DEMO_SERVICING_ENABLED',False):
        from .servicing_services import projection_for_book,display_projection
        try:
            result=projection_for_book(book)
            simulation=display_projection(result) if result else None
        except LedgerError as error:simulation_error=' '.join(error.messages)
    return render(request, 'finance/account.html' , context(request, book=book, account=account,
        simulation=simulation,simulation_error=simulation_error,servicing_enabled=getattr(settings,'DEMO_SERVICING_ENABLED',False),page=page, rows=rows, schedules=schedules, principal=money(totals['net_debit']['principal']),
        unapplied=money(-totals['net_debit']['unapplied'])))


@demo_page
@member_view
@require_http_methods(['GET', 'POST'])
def link(request, pk):
    require_editor(request)
    book = scoped_book(request, pk)
    form = LinkForm(request.POST if request.method == 'POST' else None, book=book)
    if request.method == 'POST' and 'preview_token' in request.POST:
        try:
            payload = signing.loads(request.POST['preview_token'], salt=SALT, max_age=1800)
        except signing.BadSignature:
            form.add_error(None, 'This preview expired or could not be verified. Choose the draft again.')
        else:
            if payload['actor'] != request.user.pk or payload['dealer'] != request.member.dealership_id or payload['book'] != book.pk:
                raise PermissionDenied
            try:
                link_draft(dealership_id=book.dealership_id, book_id=book.pk, deal_id=payload['deal'], actor=request.user, expected_digest=payload['digest'])
            except LedgerError as error:
                form.add_error(None, error.messages)
                return render(request, 'finance/account_link.html', context(request, book=book, form=form), status=409)
            return redirect('bhph_account', pk=book.pk)
    elif request.method == 'POST' and form.is_valid():
        snapshot = account_draft_snapshot(form.cleaned_data['deal'])
        token = signing.dumps({'actor': request.user.pk, 'dealer': book.dealership_id, 'book': book.pk,
                               'deal': form.cleaned_data['deal'].pk, 'digest': result_digest(snapshot)}, salt=SALT)
        return render(request, 'finance/account_link.html', context(request, book=book, form=form, snapshot=snapshot, token=token))
    return render(request, 'finance/account_link.html', context(request, book=book, form=form))


@demo_page
@member_view
@require_GET
@transaction.atomic
def receipt(request, pk, posting_pk):
    from django.utils import timezone
    book = scoped_book(request, pk, locked=True)
    posting = get_object_or_404(book.postings.select_related('actor', 'reversal__actor'), pk=posting_pk, kind='receipt')
    account = DemoAccountContext.objects.filter(book=book).first()
    if account and result_digest(account.snapshot) != account.snapshot_sha256:
        return render(request, 'finance/account_error.html', context(request), status=409)
    return render(request, 'finance/account_receipt.html', context(request, book=book, posting=posting,
        account=account, amount=money(posting.amount_cents), captured_at=timezone.now(),
        display_zone=str(timezone.get_current_timezone())))

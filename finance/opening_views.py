# SPDX-License-Identifier: MPL-2.0
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from core.access import member_view, context, require_editor
from deals.models import DraftDeal
from deals.account_context import account_draft_snapshot, eligible_account_drafts
from .forms import ReceiptForm
from .views import demo_page, money
from .services import cents, LedgerError
from .account_services import open_from_draft, draft_account
from .schedule_services import result_digest

SALT = 'railet.demo-draft-opening.v1'


class DraftOpeningForm(ReceiptForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['amount'].label = 'Synthetic opening principal (USD)'
        self.fields['reference'].label = 'Opening-balance source (synthetic only)'
        self.fields['reference'].help_text = 'Enter the invented reference you used for this figure. The draft balance is not copied into debt.'


@demo_page
@member_view
@require_http_methods(['GET', 'POST'])
def opening(request, pk):
    require_editor(request)
    deal = get_object_or_404(DraftDeal.objects.select_related('buyer', 'vehicle'),
                            pk=pk, dealership=request.member.dealership,
                            buyer__dealership=request.member.dealership,
                            vehicle__dealership=request.member.dealership)
    existing = draft_account(dealership_id=request.member.dealership_id, deal_id=deal.pk)
    if request.method == 'GET' and existing:
        return redirect('bhph_account', pk=existing.book_id)
    if 'preview_token' in request.POST:
        try:
            payload = signing.loads(request.POST['preview_token'], salt=SALT, max_age=1800)
        except signing.BadSignature:
            return render(request, 'finance/opening_invalid.html', context(request, deal=deal), status=400)
        if (payload['actor'], payload['dealer'], payload['deal']) != (request.user.pk, request.member.dealership_id, deal.pk):
            raise PermissionDenied
        form = DraftOpeningForm(payload['data'], dealership=request.member.dealership)
        if not form.is_valid():
            return render(request, 'finance/draft_opening.html', context(request, deal=deal, form=form), status=400)
        if request.POST.get('action') == 'edit':
            return render(request, 'finance/draft_opening.html', context(request, deal=deal, form=form))
        if request.POST.get('action') != 'open':
            return render(request, 'finance/opening_invalid.html', context(request, deal=deal), status=400)
        try:
            data=form.cleaned_data
            book,_=open_from_draft(dealership_id=request.member.dealership_id, deal_id=deal.pk,
                actor=request.user, opening_amount=data['amount'], opening_on=data['effective_on'],
                source_reference=data['reference'], request_key=data['request_key'], expected_digest=payload['digest'])
        except LedgerError as error:
            form.add_error(None, error.messages)
            return render(request, 'finance/draft_opening.html', context(request, deal=deal, form=form, existing=existing), status=409)
        return redirect('bhph_account', pk=book.pk)
    if not eligible_account_drafts(dealership_id=request.member.dealership_id, customer_id=deal.buyer_id).filter(pk=deal.pk).exists():
        return render(request, 'finance/opening_invalid.html', context(request, deal=deal), status=409)
    form=DraftOpeningForm(request.POST if request.method=='POST' else None, dealership=request.member.dealership)
    if request.method=='POST' and form.is_valid():
        data=form.cleaned_data
        snapshot=account_draft_snapshot(deal)
        values={name: (value.isoformat() if hasattr(value,'isoformat') else str(value))
                for name,value in data.items() if name!='synthetic_confirmed'}
        values['synthetic_confirmed']=True
        token=signing.dumps({'actor':request.user.pk,'dealer':request.member.dealership_id,
                            'deal':deal.pk,'digest':result_digest(snapshot),'data':values},salt=SALT)
        return render(request,'finance/draft_opening_preview.html',context(request,deal=deal,snapshot=snapshot,
            token=token,amount=money(cents(data['amount'])),opening_on=data['effective_on'],reference=data['reference']))
    return render(request,'finance/draft_opening.html',context(request,deal=deal,form=form,existing=existing))

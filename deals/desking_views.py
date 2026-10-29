# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from core.access import member_view
from .forms import DraftWorksheetForm,DraftFinanceProposalForm
from .models import DraftDeal,DraftFinanceProposal,FINANCING_TYPES,MONEY_FIELDS
from .worksheet import draft_totals
from .desking import illustrate

@member_view
@require_POST
def preview(request):
    if not getattr(settings,'FL_TAX_ESTIMATES_ENABLED',False):return JsonResponse({'ok':False,'errors':['Draft estimates are unavailable.']},status=403)
    data=request.POST.copy();data['revision']='1'
    deal=DraftDeal(dealership=request.member.dealership)
    form=DraftWorksheetForm(data,instance=deal)
    if not form.is_valid():response=JsonResponse({'ok':False,'errors':[str(e) for errors in form.errors.values() for e in errors]},status=400)
    else:
        totals=draft_totals(form.cleaned_data);result=None
        if form.cleaned_data['deal_type'] in FINANCING_TYPES:
            proposal=DraftFinanceProposalForm(data,prefix=form.cleaned_data['deal_type'],instance=DraftFinanceProposal(kind=form.cleaned_data['deal_type']))
            if proposal.is_valid():
                try:result=illustrate(balance=totals['balance'],method=proposal.cleaned_data['interest_method'],frequency=proposal.cleaned_data['payment_frequency'],count=proposal.cleaned_data['payment_count'],rate=proposal.cleaned_data['annual_contract_rate'],finance_charge=proposal.cleaned_data['illustration_finance_charge'])
                except ValidationError as error:result={'available':False,'message':' '.join(error.messages)}
            else:result={'available':False,'message':'Check financing terms before calculating.'}
        response=JsonResponse({'ok':True,'totals':{k:str(v) for k,v in totals.items()},'tax':deal.tax_context,'illustration':result})
    response['Cache-Control']='private, no-store';return response

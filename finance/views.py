# SPDX-License-Identifier: MPL-2.0
from functools import wraps
from decimal import Decimal
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.http import Http404,HttpResponse
from django.shortcuts import get_object_or_404,redirect,render
from django.core.paginator import Paginator
from django.db import transaction
from django.views.decorators.http import require_GET,require_http_methods
from core.access import context,member_view,require_editor
from .models import DemoBook,DemoPosting
from .forms import OpeningForm,ReceiptForm,ReversalForm
from .services import require_demo,open_book,record_receipt,reverse_receipt,reconcile,LedgerError

SALT='railet.ledger-demo.preview.v1'
FORMS={'opening':OpeningForm,'receipt':ReceiptForm,'reversal':ReversalForm}
LABELS={'opening':'Open a synthetic account','receipt':'Record a synthetic unapplied receipt','reversal':'Correct a synthetic receipt'}


def demo_page(view):
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        try:
            require_demo()
            response=view(request,*args,**kwargs)
        except PermissionDenied:
            response=HttpResponse(status=403)
        except Http404:
            response=HttpResponse(status=404)
        response['Cache-Control']='private, no-store'
        response['X-Content-Type-Options']='nosniff'
        return response
    return wrapped


def money(value):return f'${Decimal(value)/100:,.2f}'


def scoped_book(request,pk,locked=False):
    choices=DemoBook.objects.all()
    if locked:choices=choices.select_for_update(of=('self',))
    return get_object_or_404(choices,pk=pk,dealership=request.member.dealership,customer__dealership=request.member.dealership)


@demo_page
@member_view
@require_GET
def listing(request):
    page=Paginator(DemoBook.objects.filter(dealership=request.member.dealership,customer__dealership=request.member.dealership).select_related('customer'),25).get_page(request.GET.get('page'))
    return render(request,'finance/list.html',context(request,page=page))


@demo_page
@member_view
@require_GET
@transaction.atomic
def detail(request,pk):
    # Keep the journal page and aggregate from observing different posting states.
    book=scoped_book(request,pk,locked=True)
    balance=reconcile(dealership_id=request.member.dealership_id,book_id=book.pk)
    page=Paginator(book.postings.select_related('actor','reversal').order_by('-entered_at','-pk'),25).get_page(request.GET.get('page'))
    rows=[{'entry':entry,'amount':money(entry.amount_cents),'can_reverse':entry.kind=='receipt' and not hasattr(entry,'reversal')} for entry in page]
    return render(request,'finance/detail.html',context(request,book=book,page=page,rows=rows,principal=money(balance['net_debit']['principal']),cash_control=money(balance['net_debit']['cash_control']),unapplied=money(-balance['net_debit']['unapplied']),total_debits=money(balance['total_debits_cents']),total_credits=money(balance['total_credits_cents']),balanced=balance['balanced']))


def form_context(request,kind,form,book=None,posting=None):
    return context(request,kind=kind,form=form,book=book,posting=posting,heading=LABELS[kind],original_amount=money(posting.amount_cents) if posting else None)


@demo_page
@member_view
@require_http_methods(['GET','POST'])
def prepare(request,kind,pk=None,posting_pk=None):
    require_editor(request)
    if kind not in FORMS:raise Http404
    book=scoped_book(request,pk) if pk else None
    posting=get_object_or_404(book.postings,pk=posting_pk,kind='receipt') if posting_pk else None
    form=FORMS[kind](request.POST if request.method=='POST' else None,dealership=request.member.dealership)
    if request.method=='POST' and form.is_valid():
        if book and form.cleaned_data['effective_on']<(posting.effective_on if posting else book.opening_on):
            form.add_error('effective_on','The effective date cannot precede the opening or original receipt.')
        else:
            payload={name:(value.isoformat() if hasattr(value,'isoformat') else str(value)) for name,value in form.cleaned_data.items() if name not in ('customer','synthetic_confirmed')}
            payload['synthetic_confirmed']=True
            if kind=='opening':payload['customer']=form.cleaned_data['customer'].pk
            token=signing.dumps({'actor':request.user.pk,'dealer':request.member.dealership_id,'kind':kind,'book':book.pk if book else None,'posting':posting.pk if posting else None,'data':payload},salt=SALT)
            preview_rows=[]
            for name in ('customer','label','amount','effective_on','reference'):
                if name in form.cleaned_data:preview_rows.append((form.fields[name].label,str(form.cleaned_data[name])))
            return render(request,'finance/preview.html',context(request,heading=LABELS[kind],kind=kind,book=book,original_amount=money(posting.amount_cents) if posting else None,preview_rows=preview_rows,token=token))
    return render(request,'finance/form.html',form_context(request,kind,form,book,posting))


@demo_page
@member_view
@require_http_methods(['POST'])
def confirm(request):
    require_editor(request)
    try:payload=signing.loads(request.POST.get('preview_token',''),salt=SALT,max_age=1800)
    except signing.BadSignature:
        return render(request,'finance/invalid.html',context(request),status=400)
    if payload['actor']!=request.user.pk or payload['dealer']!=request.member.dealership_id:raise PermissionDenied
    kind=payload['kind']
    if kind not in FORMS:raise Http404
    book=scoped_book(request,payload['book']) if payload['book'] else None
    posting=get_object_or_404(book.postings,pk=payload['posting'],kind='receipt') if payload['posting'] else None
    form=FORMS[kind](payload['data'],dealership=request.member.dealership)
    if not form.is_valid():return render(request,'finance/form.html',form_context(request,kind,form,book,posting),status=400)
    if request.POST.get('action')=='edit':return render(request,'finance/form.html',form_context(request,kind,form,book,posting))
    if request.POST.get('action')!='post':return HttpResponse(status=400)
    data=form.cleaned_data
    args={'dealership_id':request.member.dealership_id,'actor':request.user,'request_key':data['request_key']}
    try:
        if kind=='opening':book,_=open_book(**args,customer_id=data['customer'].pk,label=data['label'],source_reference=data['reference'],opening_on=data['effective_on'],opening_amount=data['amount'])
        elif kind=='receipt':saved_posting,_=record_receipt(**args,book_id=book.pk,amount=data['amount'],effective_on=data['effective_on'],reason=data['reference'])
        else:reverse_receipt(**args,book_id=book.pk,posting_id=posting.pk,effective_on=data['effective_on'],reason=data['reference'])
    except LedgerError as error:
        form.add_error(None,error.messages)
        return render(request,'finance/form.html',form_context(request,kind,form,book,posting),status=409)
    if kind=='receipt':
        return redirect('bhph_account_receipt',pk=book.pk,posting_pk=saved_posting.pk)
    return redirect('bhph_account',pk=book.pk)

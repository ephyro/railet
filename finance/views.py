# SPDX-License-Identifier: MPL-2.0
from functools import wraps
from decimal import Decimal
from django.core import signing
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404,HttpResponse
from django.shortcuts import get_object_or_404,redirect,render
from django.core.paginator import Paginator
from django.db import transaction
from django.views.decorators.http import require_GET,require_http_methods
from core.access import context,member_view,require_editor
from .models import DemoBook,DemoPosting
from .forms import OpeningForm,ReceiptForm,ReversalForm
from .services import cents,require_demo,open_book,record_receipt,reverse_receipt,reconcile,LedgerError

SALT='railet.ledger-demo.preview.v1'
FORMS={'opening':OpeningForm,'receipt':ReceiptForm,'reversal':ReversalForm}
LABELS={'opening':'Open a demo account','receipt':'Record a demo payment','reversal':'Reverse a demo payment'}


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
@transaction.atomic
def listing(request):
    from urllib.parse import urlencode
    from core.filter_views import filter_context
    from .filters import SCHEMA
    from .queries import search_accounts, with_account_activity
    from django.conf import settings
    from dataclasses import replace
    servicing_enabled=getattr(settings,'DEMO_SERVICING_ENABLED',False)
    schema=SCHEMA if servicing_enabled else replace(SCHEMA,sorts={k:v for k,v in SCHEMA.sorts.items() if k!='oldest_due'})
    filters=filter_context(request,schema)
    state=filters['filter_state']
    books=search_accounts(dealership_id=request.member.dealership_id,query=state.query)
    scope=state.extra.get('scope')
    if scope:books=books.filter(has_context=scope=='linked')
    wants_worklist=bool(state.extra.get('status') or state.sort=='oldest_due')
    if wants_worklist and not servicing_enabled:
        state.errors.append('Demo status is unavailable in this workspace. Clear the status filter or choose another sort order.')
    if wants_worklist and servicing_enabled and not state.errors:
        from .account_worklist import select_worklist
        try:selected=select_worklist(books=state.apply(books),dealership_id=request.member.dealership_id,state=state)
        except LedgerError as error:
            state.errors.extend(error.messages);selected=[]
        page=Paginator(selected,25).get_page(request.GET.get('page'))
    else:
        page=Paginator(with_account_activity(state.apply(books)),25).get_page(request.GET.get('page'))
        if servicing_enabled:
            selected=list(page)
            ids=[book.pk for book in selected]
            list(DemoBook.objects.filter(pk__in=ids,dealership_id=request.member.dealership_id).order_by('pk').select_for_update())
            refreshed={b.pk:b for b in with_account_activity(search_accounts(dealership_id=request.member.dealership_id,query='').filter(pk__in=ids))}
            page.object_list=[refreshed[b.pk] for b in selected if b.pk in refreshed]
            from .servicing_services import attach_list_status
            attach_list_status(page.object_list)
    for book in page:
        from datetime import date
        book.next_unpaid_date=date.fromisoformat(book.simulation['next_unpaid_on']) if servicing_enabled and book.simulation and book.simulation['next_unpaid_on'] else None
        book.unapplied_display=money(book.activity_unapplied_cents)
        book.latest_receipt_display=money(book.latest_receipt_cents) if book.latest_receipt_cents is not None else None
    tabs=[]
    for value,label in (('', 'All accounts'),('linked','Linked to a draft'),('unlinked','Needs draft context')):
        params={key:list(values) for key,values in state.parameters.items()}
        if value:params['scope']=[value]
        else:params.pop('scope',None)
        tabs.append({'label':label,'query':urlencode(params,doseq=True),'active':(scope or '')==value})
    status_tabs=[]
    for value,label in (('', 'All accounts'),('past_due','Past due'),('due_today','Due today'),('current','Up to date'),('uncalculated','Not calculated')):
        params={key:list(values) for key,values in state.parameters.items()}
        if value:params['status']=[value]
        else:params.pop('status',None)
        if value=='past_due' and state.sort==SCHEMA.default_sort:params['sort']=['oldest_due']
        status_tabs.append({'label':label,'query':urlencode(params,doseq=True),'active':(state.extra.get('status') or '')==value,'status':value})
    return render(request,'finance/list.html',context(request,**filters,page=page,page_obj=page,tabs=tabs,status_tabs=status_tabs,servicing_enabled=servicing_enabled,
        quick_filter_label=dict((('linked','Linked to a draft'),('unlinked','Needs draft context'))).get(scope,'')))


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


def payment_review(request,*,kind,book,posting,form,payload_data,changed=False):
    state=None;impact=None
    if kind in ('receipt','reversal'):
        from .servicing_services import payment_impact
        state,impact=payment_impact(book,amount=form.cleaned_data.get('amount'),effective_on=form.cleaned_data['effective_on'],reversal=posting if kind=='reversal' else None)
    token=signing.dumps({'actor':request.user.pk,'dealer':request.member.dealership_id,'kind':kind,
        'book':book.pk if book else None,'posting':posting.pk if posting else None,'data':payload_data,
        'servicing_state':state},salt=SALT)
    rows=[(form.fields[name].label,dict(DemoPosting.PaymentMethod.choices).get(form.cleaned_data[name],str(form.cleaned_data[name])) if name=='payment_method' else str(form.cleaned_data[name])) for name in ('customer','label','amount','payment_method','effective_on','reference') if name in form.cleaned_data]
    return render(request,'finance/preview.html',context(request,heading=LABELS[kind],kind=kind,book=book,
        original_amount=money(posting.amount_cents) if posting else None,posting=posting,preview_rows=rows,token=token,
        payment_impact=impact,impact_changed=changed),status=409 if changed else 200)


@demo_page
@member_view
@require_http_methods(['GET','POST'])
@transaction.atomic
def prepare(request,kind,pk=None,posting_pk=None):
    require_editor(request)
    if kind not in FORMS:raise Http404
    book=scoped_book(request,pk,locked=request.method=='POST') if pk else None
    posting=get_object_or_404(book.postings,pk=posting_pk,kind='receipt') if posting_pk else None
    form=FORMS[kind](request.POST if request.method=='POST' else None,dealership=request.member.dealership)
    if request.method=='POST' and form.is_valid():
        if book and form.cleaned_data['effective_on']<(posting.effective_on if posting else book.opening_on):
            form.add_error('effective_on','The effective date cannot precede the opening or original receipt.')
        else:
            if kind in ('receipt','reversal'):
                prior=book.postings.filter(request_key=form.cleaned_data['request_key']).first()
                if prior:
                    data=form.cleaned_data
                    expected=('receipt',cents(data['amount']),None) if kind=='receipt' else ('reversal',posting.amount_cents,posting.pk)
                    if (prior.kind,prior.amount_cents,prior.reverses_id,prior.reason,prior.effective_on,prior.actor_id,prior.payment_method)!=(*expected,data['reference'],data['effective_on'],request.user.pk,data.get('payment_method',posting.payment_method if posting else 'unspecified')):
                        form.add_error(None,'This posting key was used for different facts. Start a fresh payment form.')
                        return render(request,'finance/form.html',form_context(request,kind,form,book,posting),status=409)
                    messages.info(request,'This demo posting was already recorded. Its original receipt is shown below.')
                    return redirect('bhph_account_receipt',pk=book.pk,posting_pk=prior.pk if kind=='receipt' else posting.pk)
            payload={name:(value.isoformat() if hasattr(value,'isoformat') else str(value)) for name,value in form.cleaned_data.items() if name not in ('customer','synthetic_confirmed')}
            payload['synthetic_confirmed']=True
            if kind=='opening':payload['customer']=form.cleaned_data['customer'].pk
            try:return payment_review(request,kind=kind,book=book,posting=posting,form=form,payload_data=payload)
            except LedgerError as error:form.add_error(None,error.messages)
    return render(request,'finance/form.html',form_context(request,kind,form,book,posting))


@demo_page
@member_view
@require_http_methods(['POST'])
@transaction.atomic
def confirm(request):
    require_editor(request)
    try:payload=signing.loads(request.POST.get('preview_token',''),salt=SALT,max_age=1800)
    except signing.BadSignature:
        return render(request,'finance/invalid.html',context(request),status=400)
    if payload['actor']!=request.user.pk or payload['dealer']!=request.member.dealership_id:raise PermissionDenied
    kind=payload['kind']
    if kind not in FORMS:raise Http404
    book=scoped_book(request,payload['book'],locked=True) if payload['book'] else None
    posting=get_object_or_404(book.postings,pk=payload['posting'],kind='receipt') if payload['posting'] else None
    form=FORMS[kind](payload['data'],dealership=request.member.dealership)
    if not form.is_valid():return render(request,'finance/form.html',form_context(request,kind,form,book,posting),status=400)
    if request.POST.get('action')=='edit':return render(request,'finance/form.html',form_context(request,kind,form,book,posting))
    if request.POST.get('action')!='post':return HttpResponse(status=400)
    data=form.cleaned_data
    args={'dealership_id':request.member.dealership_id,'actor':request.user,'request_key':data['request_key']}
    try:
        if kind in ('receipt','reversal') and not book.postings.filter(request_key=data['request_key']).exists():
            from .servicing_services import payment_impact
            state,_=payment_impact(book,amount=data.get('amount'),effective_on=data['effective_on'],reversal=posting if kind=='reversal' else None)
            if payload.get('servicing_state')!=state:
                return payment_review(request,kind=kind,book=book,posting=posting,form=form,payload_data=payload['data'],changed=True)
        if kind=='opening':book,_=open_book(**args,customer_id=data['customer'].pk,label=data['label'],source_reference=data['reference'],opening_on=data['effective_on'],opening_amount=data['amount'])
        elif kind=='receipt':saved_posting,_=record_receipt(**args,book_id=book.pk,amount=data['amount'],effective_on=data['effective_on'],reason=data['reference'],payment_method=data['payment_method'])
        else:reverse_receipt(**args,book_id=book.pk,posting_id=posting.pk,effective_on=data['effective_on'],reason=data['reference'])
    except LedgerError as error:
        form.add_error(None,error.messages)
        return render(request,'finance/form.html',form_context(request,kind,form,book,posting),status=409)
    if kind in ('receipt','reversal'):
        return redirect('bhph_account_receipt',pk=book.pk,posting_pk=saved_posting.pk if kind=='receipt' else posting.pk)
    return redirect('bhph_account',pk=book.pk)

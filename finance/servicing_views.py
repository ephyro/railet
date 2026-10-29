# SPDX-License-Identifier: MPL-2.0
from uuid import uuid4
from django import forms
from django.conf import settings
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404,redirect,render
from django.utils import timezone
from django.views.decorators.http import require_GET,require_http_methods
from core.access import context,member_view,require_editor
from .views import demo_page,scoped_book
from .models import DemoSchedule,DemoServicingPlan
from .services import LedgerError
from .servicing import POLICY
from .servicing_services import require_simulation,verified_schedule,select_baseline,projection_for_book,display_projection

SALT='railet.servicing.selection.v1'

class BaselineForm(forms.Form):
    schedule=forms.ModelChoiceField(queryset=DemoSchedule.objects.none(),label='Monthly precomputed illustration')
    reason=forms.CharField(max_length=300,label='Why use this demo schedule?',widget=forms.Textarea(attrs={'rows':2}))
    creation_key=forms.UUIDField(initial=uuid4,widget=forms.HiddenInput)
    synthetic_confirmed=forms.BooleanField(label='I understand this is an installment-coverage simulation, not live servicing or a payoff.')
    def __init__(self,*args,book,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['schedule'].queryset=book.schedule_illustrations.filter(method='precomputed',inputs__frequency='monthly')
        self.fields['schedule'].label_from_instance=lambda s:f'Illustration #{s.pk} · {s.inputs.get("count")} monthly installments · first due {s.inputs.get("first_due_on")}'


@demo_page
@member_view
@require_http_methods(['GET','POST'])
def setup(request,pk):
    require_simulation();require_editor(request);book=scoped_book(request,pk)
    if request.method=='GET' and DemoServicingPlan.objects.filter(book=book).exists():return redirect('servicing_detail',pk=pk)
    form=BaselineForm(request.POST if request.method=='POST' else None,book=book)
    if 'preview_token' in request.POST:
        try:payload=signing.loads(request.POST['preview_token'],salt=SALT,max_age=1800)
        except signing.BadSignature:return render(request,'finance/servicing_invalid.html',context(request,book=book),status=400)
        if (payload['actor'],payload['dealer'],payload['book'],payload['policy'])!=(request.user.pk,request.member.dealership_id,book.pk,POLICY):raise PermissionDenied
        form=BaselineForm(payload['data'],book=book)
        if form.is_valid():
            if request.POST.get('action')=='edit':return render(request,'finance/servicing_setup.html',context(request,book=book,form=form))
            if request.POST.get('action')!='choose':return render(request,'finance/servicing_invalid.html',context(request,book=book),status=400)
            try:
                data=form.cleaned_data
                select_baseline(dealership_id=request.member.dealership_id,book_id=book.pk,schedule_id=data['schedule'].pk,actor=request.user,reason=data['reason'],creation_key=data['creation_key'],expected_digest=payload['digest'])
            except LedgerError as error:form.add_error(None,error.messages)
            else:return redirect('servicing_detail',pk=book.pk)
        return render(request,'finance/servicing_setup.html',context(request,book=book,form=form),status=409)
    if request.method=='POST' and form.is_valid():
        try:result=verified_schedule(book,form.cleaned_data['schedule'])
        except LedgerError as error:form.add_error(None,error.messages)
        else:
            data={name:(value.pk if name=='schedule' else str(value)) for name,value in form.cleaned_data.items()}
            data['synthetic_confirmed']=True
            token=signing.dumps({'actor':request.user.pk,'dealer':request.member.dealership_id,'book':book.pk,'policy':POLICY,'data':data,'digest':form.cleaned_data['schedule'].result_sha256},salt=SALT,compress=True)
            return render(request,'finance/servicing_preview.html',context(request,book=book,token=token,schedule=form.cleaned_data['schedule'],result=result,reason=form.cleaned_data['reason']))
    return render(request,'finance/servicing_setup.html',context(request,book=book,form=form))


class AsOfForm(forms.Form):
    as_of=forms.DateField(label='As of date',initial=timezone.localdate,widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))


@demo_page
@member_view
@require_GET
@transaction.atomic
def detail(request,pk):
    require_simulation();book=scoped_book(request,pk,locked=True)
    plan=DemoServicingPlan.objects.select_related('schedule','created_by').filter(book=book).first()
    if not plan:return redirect('bhph_account',pk=pk)
    form=AsOfForm(request.GET if 'as_of' in request.GET else {'as_of':timezone.localdate().isoformat()})
    projection=None;error=None
    if form.is_valid():
        try:projection=display_projection(projection_for_book(book,as_of=form.cleaned_data['as_of'],plan=plan))
        except LedgerError as problem:error=' '.join(problem.messages)
    page=Paginator(projection['display_rows'] if projection else [],25).get_page(request.GET.get('page'))
    return render(request,'finance/servicing_detail.html',context(request,book=book,plan=plan,form=form,simulation=projection,error=error,page=page),status=400 if form.errors or error else 200)

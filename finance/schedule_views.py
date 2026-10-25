# SPDX-License-Identifier: MPL-2.0
from uuid import uuid4
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404,render,redirect
from django.views.decorators.http import require_GET,require_http_methods
from core.access import member_view,context,require_editor
from .views import demo_page,scoped_book,money
from .models import DemoSchedule
from .schedule_forms import ScheduleForm
from .schedule_services import calculate_for_book,result_digest,save_illustration
from .services import LedgerError

SALT='railet.schedule.preview.v1'


def rows_for_display(result,rows):
    return [{'number':row['number'],'due_on':row['due_on'],'payment':money(row['payment_cents']),
             'balance':money(row.get('remaining_scheduled_cents',row.get('remaining_principal_cents'))),
             'interest':money(row['interest_cents']) if 'interest_cents' in row else None,
             'principal':money(row['principal_cents']) if 'principal_cents' in row else None} for row in rows]


def calculation_context(result):
    return {'result':result,'rows':rows_for_display(result,result['rows']),
            'principal':money(result['principal_cents']),'charge':money(result['finance_charge_cents']),
            'total':money(result['total_payments_cents'])}


@demo_page
@member_view
@require_http_methods(['GET','POST'])
def prepare(request,pk):
    require_editor(request);book=scoped_book(request,pk)
    form=ScheduleForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        inputs=form.calculation_inputs()
        try:result=calculate_for_book(book,inputs)
        except LedgerError as error:form.add_error(None,error.messages)
        else:
            token=signing.dumps({'actor':request.user.pk,'dealer':request.member.dealership_id,'book':book.pk,'key':str(uuid4()),'inputs':inputs,'digest':result_digest(result)},salt=SALT,compress=True)
            return render(request,'finance/schedule_preview.html',context(request,book=book,form=form,token=token,**calculation_context(result)))
    return render(request,'finance/schedule_form.html',context(request,book=book,form=form))


@demo_page
@member_view
@require_http_methods(['POST'])
def confirm(request):
    require_editor(request)
    try:payload=signing.loads(request.POST.get('preview_token',''),salt=SALT,max_age=1800)
    except signing.BadSignature:return render(request,'finance/schedule_invalid.html',context(request),status=400)
    if payload['actor']!=request.user.pk or payload['dealer']!=request.member.dealership_id:raise PermissionDenied
    book=scoped_book(request,payload['book'])
    form=ScheduleForm({**payload['inputs'],'synthetic_confirmed':True})
    if not form.is_valid():return render(request,'finance/schedule_form.html',context(request,book=book,form=form),status=400)
    if request.POST.get('action')=='edit':return render(request,'finance/schedule_form.html',context(request,book=book,form=form))
    if request.POST.get('action')!='save':return HttpResponse(status=400)
    try:
        illustration,_=save_illustration(dealership_id=request.member.dealership_id,book_id=book.pk,actor=request.user,inputs=form.calculation_inputs(),expected_digest=payload['digest'],creation_key=payload['key'])
    except LedgerError as error:
        form.add_error(None,error.messages)
        return render(request,'finance/schedule_form.html',context(request,book=book,form=form),status=409)
    return redirect('schedule_detail',pk=book.pk,scenario_pk=illustration.pk)


@demo_page
@member_view
@require_GET
def listing(request,pk):
    book=scoped_book(request,pk)
    page=Paginator(book.schedule_illustrations.select_related('created_by'),25).get_page(request.GET.get('page'))
    return render(request,'finance/schedule_list.html',context(request,book=book,page=page))


@demo_page
@member_view
@require_GET
def detail(request,pk,scenario_pk):
    book=scoped_book(request,pk)
    illustration=get_object_or_404(DemoSchedule,pk=scenario_pk,book=book)
    if result_digest(illustration.result)!=illustration.result_sha256:
        return HttpResponse('Saved illustration integrity check failed. Contact your administrator.',status=409,content_type='text/plain')
    display=calculation_context(illustration.result)
    page=Paginator(illustration.result['rows'],25).get_page(request.GET.get('page'))
    display['rows']=rows_for_display(illustration.result,page)
    return render(request,'finance/schedule_detail.html',context(request,book=book,illustration=illustration,page=page,**display))

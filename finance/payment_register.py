# SPDX-License-Identifier: MPL-2.0
"""Read-only synthetic receipt register; no settlement or allocation decisions."""
from datetime import datetime,time,timedelta
from urllib.parse import urlencode
from django import forms
from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET
from core.access import member_view,context
from .models import DemoPosting
from .views import demo_page,money

MAX_ROWS=5000
MAX_DAYS=92


class RegisterForm(forms.Form):
    basis=forms.ChoiceField(label='Show entries by',choices=[('recorded','Date recorded'),('effective','Effective date')])
    start=forms.DateField(label='From',input_formats=['%Y-%m-%d'],widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    end=forms.DateField(label='Through',input_formats=['%Y-%m-%d'],widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))

    def clean(self):
        data=super().clean();start=data.get('start');end=data.get('end')
        if start and end:
            if start>end:raise forms.ValidationError('The start date must be on or before the end date.')
            if (end-start).days>=MAX_DAYS:raise forms.ValidationError(f'Choose up to {MAX_DAYS} days for this register.')
            if start.year<1900 or end.year>2100:raise forms.ValidationError('Choose dates between 1900 and 2100 for this rehearsal.')
            if end>timezone.localdate():self.add_error('end','Choose today or an earlier date.')
        return data


def date_supported(day):return 1900<=day.year<=2100


def capture(*,dealership_id,start,end,basis):
    """One bounded database read; displayed rows and sums use the same capture."""
    entries=DemoPosting.objects.filter(book__dealership_id=dealership_id,
        book__customer__dealership_id=dealership_id,kind__in=['receipt','reversal'])
    if basis=='recorded':
        zone=timezone.get_current_timezone()
        left=timezone.make_aware(datetime.combine(start,time.min),zone)
        right=timezone.make_aware(datetime.combine(end+timedelta(days=1),time.min),zone)
        entries=entries.filter(entered_at__gte=left,entered_at__lt=right).order_by('-entered_at','-pk')
    else:
        entries=entries.filter(effective_on__range=(start,end)).order_by('-effective_on','-entered_at','-pk')
    rows=list(entries.select_related('book__customer','actor')[:MAX_ROWS+1])
    if len(rows)>MAX_ROWS:raise ValueError('Too many entries for this report. Narrow the date range; no partial totals are shown.')
    receipts=sum(p.amount_cents for p in rows if p.kind=='receipt')
    corrections=sum(p.amount_cents for p in rows if p.kind=='reversal')
    return rows,{'receipts_cents':receipts,'corrections_cents':corrections,'net_cents':receipts-corrections,
                 'receipt_count':sum(p.kind=='receipt' for p in rows),'correction_count':sum(p.kind=='reversal' for p in rows),
                 'methods':method_totals(rows)}


def method_totals(rows):
    """Same captured journal; no method guesses or independent aggregate query."""
    result=[]
    for method in (DemoPosting.PaymentMethod.CASH,DemoPosting.PaymentMethod.CHECK,DemoPosting.PaymentMethod.OTHER,DemoPosting.PaymentMethod.UNSPECIFIED):
        label=method.label
        selected=[p for p in rows if p.payment_method==method]
        receipts=sum(p.amount_cents for p in selected if p.kind=='receipt')
        reversals=sum(p.amount_cents for p in selected if p.kind=='reversal')
        result.append({'method':method,'label':label,'receipts_cents':receipts,'reversals_cents':reversals,
            'net_cents':receipts-reversals,'count':len(selected),'receipts':money(receipts),
            'reversals':money(reversals),'net':signed_money(receipts-reversals)})
    return result


def signed_money(cents):
    return '-'+money(-cents) if cents<0 else money(cents)


@demo_page
@member_view
@require_GET
def register(request):
    today=timezone.localdate().isoformat();params=request.GET.copy()
    for key,value in (('basis','recorded'),('start',today),('end',today)):params.setdefault(key,value)
    form=RegisterForm(params);entries=[];totals=None
    if form.is_valid():
        try:entries,totals=capture(dealership_id=request.member.dealership_id,**form.cleaned_data)
        except ValueError as error:form.add_error(None,str(error))
    selected_day=form.cleaned_data.get('start') if form.is_valid() and form.cleaned_data['start']==form.cleaned_data['end'] else None
    links=[]
    if selected_day:
        for offset,label in ((-1,'Previous day'),(1,'Next day')):
            day=selected_day+timedelta(days=offset)
            if date_supported(day) and day<=timezone.localdate():
                links.append({'label':label,'query':urlencode({'basis':params.get('basis'),'start':day.isoformat(),'end':day.isoformat()})})
    page=Paginator(entries,25).get_page(request.GET.get('page'))
    rows=[{'entry':p,'amount':signed_money(p.amount_cents if p.kind=='receipt' else -p.amount_cents)} for p in page]
    return render(request,'finance/payment_register.html',context(request,form=form,page_obj=page,rows=rows,
        totals=totals,selected_day=selected_day,day_links=links,today=timezone.localdate(),
        custom_range=not form.is_valid() or params.get('basis')!='recorded' or selected_day is None,receipts=money(totals['receipts_cents']) if totals else None,
        corrections=money(totals['corrections_cents']) if totals else None,
        net=signed_money(totals['net_cents']) if totals else None,
        basis=params.get('basis'),display_zone=str(timezone.get_current_timezone()),
        pagination_query=urlencode({key:params.get(key) for key in ('basis','start','end')})))

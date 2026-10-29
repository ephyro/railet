# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from django import forms
from django.conf import settings
from django.utils import timezone
from .florida_tax import COUNTIES,estimate

TAX_FIELDS=('tax_mode','tax_county','tax_date','tax_trade_confirmed','tax_title_confirmed','tax_reason')


def configure_tax(form,*,new=False):
    saved=form.instance.tax_context
    form.tax_context_invalid=not isinstance(saved,dict)
    saved=saved if isinstance(saved,dict) else {}
    enabled=getattr(settings,'FL_TAX_ESTIMATES_ENABLED',False)
    initial_mode=saved.get('mode','manual') if form.instance.pk else ('fl' if new and enabled else 'manual')
    form.fields.update({
        'tax_mode':forms.ChoiceField(label='Tax calculation',choices=[('fl','Automatic · Florida resident retail sale'),('manual','Manual / special case review')],required=False),
        'tax_county':forms.ChoiceField(label='Purchaser registration county',choices=[('','Choose Florida county'),*((c,c) for c in COUNTIES)],required=False),
        'tax_date':forms.DateField(label='Proposed sale date',required=False,widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'})),
        'tax_trade_confirmed':forms.BooleanField(label='Trade is accepted for resale in this same transaction',required=False),
        'tax_title_confirmed':forms.BooleanField(label='Title / tag amounts are separately stated government fees only',required=False),
        'tax_reason':forms.CharField(label='Reason for manual tax entry',max_length=300,required=False,widget=forms.TextInput),
    })
    values={'tax_mode':initial_mode,'tax_county':saved.get('county',''),'tax_date':saved.get('date',timezone.localdate()),
            'tax_trade_confirmed':saved.get('trade_confirmed',False),'tax_title_confirmed':saved.get('title_confirmed',False),'tax_reason':saved.get('reason','')}
    form.initial.update(values)
    if form.is_bound:
        data=form.data.copy()
        # Compatibility: an old form without new tax controls preserves its prior profile.
        if 'tax_mode' not in data:
            for name,value in values.items():data[name]=value if name!='tax_mode' or form.instance.pk else 'manual'
        if data.get('tax_mode')=='fl':data['tax']=str(form.instance.tax)
        form.data=data
    form.fields['tax'].label='Sales tax estimate'
    form.fields['tax'].widget.attrs['data-tax-amount']=''
    if (form.data.get('tax_mode') if form.is_bound else initial_mode)=='fl':form.fields['tax'].widget.attrs['readonly']=True
    if not enabled:form.fields['tax_mode'].choices=[('manual','Manual / special case review')]


def clean_tax(form,data):
    if getattr(form,'tax_context_invalid',False):form.add_error(None,'Saved tax information could not be verified. Contact your administrator before changing this draft.');return
    mode=data.get('tax_mode') or 'manual'
    if mode=='fl':
        if not getattr(settings,'FL_TAX_ESTIMATES_ENABLED',False):form.add_error('tax_mode','Automatic estimates are unavailable in this workspace.');return
        if not data.get('tax_county'):form.add_error('tax_county','Choose the purchaser’s registration county to calculate tax.');return
        if not data.get('tax_date'):form.add_error('tax_date','Choose a proposed sale date.');return
        if data.get('trade_allowance') and not data.get('tax_trade_confirmed'):
            form.add_error('tax_trade_confirmed','Confirm this trade qualifies, or use manual review.');return
        if data.get('title_registration') and not data.get('tax_title_confirmed'):
            form.add_error('tax_title_confirmed','Confirm these are government fees only, or use Dealer fee for service charges.');return
        person=data.get('buyer') or getattr(form.instance,'buyer',None)
        if person and (person.region.strip().upper() not in ('','FL','FLORIDA') or person.country.strip().upper() not in ('','US','USA','UNITED STATES','UNITED STATES OF AMERICA')):
            form.add_error('tax_mode','This customer has an out-of-state address. Use manual tax review.');return
        names=('sale_price','dealer_fee','trade_allowance','title_registration')
        if any(data.get(name) is None for name in names):return
        try:context=estimate(county=data['tax_county'],on=data['tax_date'],**{name:data[name] for name in names},trade_confirmed=data.get('tax_trade_confirmed',False),title_confirmed=data.get('tax_title_confirmed',False))
        except forms.ValidationError as error:form.add_error(None,error);return
        data['tax']=Decimal(context['total']);form.instance.tax_context=context
    else:
        explicit='tax_mode' in getattr(form,'original_data',{})
        if explicit and not data.get('tax_reason'):
            form.add_error('tax_reason','Record why this draft uses a manually entered tax amount.');return
        form.instance.tax_context={'mode':'manual','reason':data.get('tax_reason',''),'total':str(data.get('tax'))} if explicit else (form.instance.tax_context or {})

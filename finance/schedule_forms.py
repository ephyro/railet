# SPDX-License-Identifier: MPL-2.0
from django import forms
from .schedules import METHODS,FREQUENCIES


class ScheduleForm(forms.Form):
    method=forms.ChoiceField(label='Illustration method',choices=[('','Choose explicitly'),*METHODS])
    frequency=forms.ChoiceField(label='Payment frequency',initial='monthly',choices=[('','Choose explicitly'),*FREQUENCIES])
    first_due_on=forms.DateField(label='First due date',input_formats=['%Y-%m-%d'],widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    count=forms.IntegerField(label='Number of installments',min_value=1,max_value=600)
    first_day=forms.IntegerField(label='Twice-monthly first day (1–28)',required=False,min_value=1,max_value=28)
    second_day=forms.IntegerField(label='Twice-monthly second day (1–28)',required=False,min_value=1,max_value=28)
    finance_charge=forms.CharField(label='Precomputed: supplied total finance charge (USD)',required=False,max_length=30,widget=forms.TextInput(attrs={'inputmode':'decimal'}))
    contract_rate=forms.CharField(label='Daily simple: annual contract rate %, not APR',required=False,max_length=30,widget=forms.TextInput(attrs={'inputmode':'decimal'}))
    regular_payment=forms.CharField(label='Daily simple: regular assumed payment (USD)',required=False,max_length=30,widget=forms.TextInput(attrs={'inputmode':'decimal'}))
    synthetic_confirmed=forms.BooleanField(label='This is an invented illustration, not contract terms, an APR disclosure, an allocation, or a payoff quote.')

    def calculation_inputs(self):
        inputs={}
        for name,value in self.cleaned_data.items():
            if name=='synthetic_confirmed':continue
            if name=='first_due_on':value=value.isoformat()
            elif name in ('finance_charge','contract_rate','regular_payment'):value=value or None
            inputs[name]=value
        return inputs

# SPDX-License-Identifier: MPL-2.0
import uuid
from django import forms
from django.utils import timezone
from customers.forms import CustomerChoiceField
from customers.models import Customer
from .services import cents,LedgerError
from .models import DemoPosting


class ReceiptForm(forms.Form):
    amount = forms.CharField(label='Payment amount (USD)', max_length=30, widget=forms.TextInput(attrs={'inputmode':'decimal'}))
    payment_method = forms.ChoiceField(label='Payment method',choices=DemoPosting.PaymentMethod.choices,initial='unspecified',required=False)
    effective_on = forms.DateField(label='Effective date',initial=timezone.localdate,input_formats=['%Y-%m-%d'],widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    reference = forms.CharField(label='Reference or note',max_length=300,widget=forms.Textarea(attrs={'rows':3}))
    request_key = forms.UUIDField(initial=uuid.uuid4,widget=forms.HiddenInput)
    synthetic_confirmed = forms.BooleanField(label='These are invented evaluation figures, not real customer funds or debt.')

    def __init__(self,*args,dealership,**kwargs):
        super().__init__(*args,**kwargs)

    def clean_payment_method(self):return self.cleaned_data['payment_method'] or 'unspecified'

    def clean_amount(self):
        value=self.cleaned_data['amount']
        try:cents(value)
        except LedgerError as error:raise forms.ValidationError(error.messages)
        return value

    def clean_effective_on(self):
        value=self.cleaned_data['effective_on']
        if value>timezone.localdate():raise forms.ValidationError('Use today or an earlier effective date for this rehearsal.')
        return value


class OpeningForm(ReceiptForm):
    customer=CustomerChoiceField(label='Existing synthetic customer',queryset=Customer.objects.none())
    label=forms.CharField(label='Demo account label',max_length=100)

    def __init__(self,*args,dealership,**kwargs):
        super().__init__(*args,dealership=dealership,**kwargs)
        self.fields.pop('payment_method')
        self.fields['customer'].queryset=Customer.objects.filter(dealership=dealership)
        self.fields['amount'].label='Synthetic opening principal (USD)'
        self.fields['reference'].label='Opening-balance source and provenance (synthetic only)'
        self.order_fields(['customer','label','amount','effective_on','reference','synthetic_confirmed','request_key'])


class ReversalForm(ReceiptForm):
    amount=None
    payment_method=None
    reference=forms.CharField(label='Reason for reversal',max_length=300,widget=forms.Textarea(attrs={'rows':3}))

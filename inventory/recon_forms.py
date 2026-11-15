# SPDX-License-Identifier: MPL-2.0
import uuid
from decimal import Decimal
from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.models import Membership
from .models import VehicleVendor, ReconTask, VehicleCostEntry


def _staff_queryset(dealership):
    return get_user_model().objects.filter(
        is_active=True,
        membership__dealership=dealership,
        membership__role__in=[Membership.Role.OWNER, Membership.Role.STAFF],
    ).order_by('username')


class VendorForm(forms.Form):
    request_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    vendor = forms.ModelChoiceField(queryset=VehicleVendor.objects.none(), required=False, label='Vendor', empty_label='No vendor selected')
    new_vendor = forms.CharField(max_length=120, required=False, label='Or add a vendor', help_text='Leave blank if you chose an existing vendor.')

    def __init__(self, *args, dealership, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vendor'].queryset = VehicleVendor.objects.filter(dealership=dealership)

    def clean(self):
        data = super().clean()
        if data.get('vendor') and data.get('new_vendor'):
            self.add_error('new_vendor', 'Choose an existing vendor or add a new one.')
        return data


class TaskForm(VendorForm):
    title = forms.CharField(max_length=160, label='Work to do', help_text='For example: replace front tires.')
    detail = forms.CharField(max_length=2000, required=False, label='Details (optional)', widget=forms.Textarea(attrs={'rows': 3}), help_text='Operational notes only. Use invented details in this test workspace.')
    assigned_to = forms.ModelChoiceField(queryset=get_user_model().objects.none(), required=False, label='Assigned to (optional)', empty_label='Unassigned')
    due_on = forms.DateField(required=False, label='Target date (optional)', input_formats=['%Y-%m-%d'], widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    field_order = ['request_key', 'title', 'detail', 'vendor', 'new_vendor', 'assigned_to', 'due_on']

    def __init__(self, *args, dealership, **kwargs):
        super().__init__(*args, dealership=dealership, **kwargs)
        self.fields['assigned_to'].queryset = _staff_queryset(dealership)


class TaskEditForm(TaskForm):
    revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    status = forms.ChoiceField(choices=ReconTask.Status.choices, label='Work status')
    field_order = ['revision', 'title', 'detail', 'status', 'vendor', 'new_vendor', 'assigned_to', 'due_on']

    def __init__(self, *args, dealership, **kwargs):
        super().__init__(*args, dealership=dealership, **kwargs)
        self.fields.pop('request_key', None)


class CostForm(VendorForm):
    category = forms.ChoiceField(choices=VehicleCostEntry.Category.choices, label='Cost type')
    description = forms.CharField(max_length=180, label='Description')
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'), label='Amount (USD)')
    effective_on = forms.DateField(initial=timezone.localdate, label='Cost date', widget=forms.DateInput(attrs={'type': 'date'}))
    task = forms.ModelChoiceField(queryset=ReconTask.objects.none(), required=False, label='Related work', empty_label='No task linked')
    field_order = ['request_key', 'category', 'description', 'amount', 'effective_on', 'vendor', 'new_vendor', 'task']

    def __init__(self, *args, vehicle, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['task'].queryset = ReconTask.objects.filter(vehicle=vehicle)

    def clean_effective_on(self):
        date = self.cleaned_data['effective_on']
        if date > timezone.localdate():
            raise forms.ValidationError('Use today or an earlier date. Planned work belongs in the work list.')
        return date


class TaskStatusForm(forms.Form):
    revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    status = forms.ChoiceField(choices=ReconTask.Status.choices, label='Work status')


class CostReversalForm(forms.Form):
    request_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    reason = forms.CharField(max_length=300, label='Reason for correction', widget=forms.Textarea(attrs={'rows': 3}))


class VendorProfileForm(forms.Form):
    request_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    revision = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)
    name = forms.CharField(max_length=120, label='Vendor name')
    contact_name = forms.CharField(max_length=120, required=False, label='Contact person (optional)')
    phone = forms.CharField(max_length=40, required=False, label='Phone (optional)', widget=forms.TextInput(attrs={'type': 'tel'}))
    email = forms.EmailField(required=False, label='Email (optional)')
    address = forms.CharField(max_length=240, required=False, label='Address (optional)')
    notes = forms.CharField(max_length=1000, required=False, label='Notes (optional)', widget=forms.Textarea(attrs={'rows': 3}), help_text='Operational vendor notes only. Do not enter tax IDs, bank details, or payment credentials.')

    def __init__(self, *args, editing=False, **kwargs):
        super().__init__(*args, **kwargs)
        if editing:
            self.fields.pop('request_key', None)
            self.fields['revision'].required = True
        else:
            self.fields.pop('revision', None)

    def clean(self):
        data = super().clean()
        for key in ('name', 'contact_name', 'phone', 'email', 'address', 'notes'):
            if key in data and isinstance(data[key], str):
                data[key] = data[key].strip()
        if 'name' in data and data['name']:
            normalized = ' '.join(data['name'].split())
            if not normalized or len(normalized) > 120 or len(normalized.casefold()) > 120:
                self.add_error('name', 'Use a vendor name of up to 120 characters.')
            else:
                data['name'] = normalized
        if 'address' in data and any(ch in data['address'] for ch in ('\r', '\n')):
            self.add_error('address', 'Enter the address on a single line.')
        return data

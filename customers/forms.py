# SPDX-License-Identifier: MPL-2.0
from django import forms
from django.db.models import Q
from .models import Customer, phone_key

class CustomerChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, customer):
        contact = customer.phone or customer.email
        identity = f"{customer} — {contact}" if contact else str(customer)
        return f"{identity} · Customer #{customer.pk}"

class CustomerForm(forms.ModelForm):
    confirm_duplicate = forms.BooleanField(required=False, label="I checked the matches. This is a different person.")
    revision = forms.IntegerField(widget=forms.HiddenInput, required=False, min_value=1)
    class Meta:
        model = Customer
        fields = ["first_name", "last_name", "phone", "email"]
        labels = {"phone": "Phone (optional)", "email": "Email (optional)"}
        widgets = {"phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}), "email": forms.EmailInput(attrs={"autocomplete": "email"}), "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}), "last_name": forms.TextInput(attrs={"autocomplete": "family-name"})}
    def __init__(self, *args, dealership, **kwargs):
        super().__init__(*args, **kwargs)
        self.dealership = dealership
        self.matches = Customer.objects.none()
        if self.instance.pk:
            self.fields["revision"].required = True
            self.initial["revision"] = self.instance.revision
    def clean(self):
        data = super().clean()
        for key in ("first_name", "last_name", "email", "phone"):
            if key in data:
                data[key] = data[key].strip()
        first, last = data.get("first_name"), data.get("last_name")
        if first and last:
            match = Q(first_name__iexact=first, last_name__iexact=last)
            if data.get("email"):
                match |= Q(email_normalized=data["email"].casefold())
            if phone_key(data.get("phone", "")):
                match |= Q(phone_normalized=phone_key(data["phone"]))
            self.matches = Customer.objects.filter(dealership=self.dealership).filter(match).exclude(pk=self.instance.pk)
            if self.matches.exists() and not data.get("confirm_duplicate"):
                self.add_error(None, "A customer with matching details already exists. Check the matches before creating another record.")
        return data

# SPDX-License-Identifier: MPL-2.0
from django import forms
from django.db.models import Q
from .models import Customer, phone_key, ADDRESS_FIELDS

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
        fields = ["first_name", "last_name", "phone", "email", *ADDRESS_FIELDS]
        labels = {"phone": "Phone (optional)", "email": "Email (optional)", "address_line1": "Street address", "address_line2": "Apartment / suite", "city": "City", "region": "State / region", "postal_code": "ZIP / postal code", "country": "Country"}
        widgets = {"phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}), "email": forms.EmailInput(attrs={"autocomplete": "email"}), "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}), "last_name": forms.TextInput(attrs={"autocomplete": "family-name"})}
    def __init__(self, *args, dealership, **kwargs):
        instance = kwargs.get('instance')
        posted = args[0] if args else kwargs.get('data')
        if instance is not None and instance.pk and posted is not None:
            posted = posted.copy()
            prefix = kwargs.get('prefix')
            for name in ADDRESS_FIELDS:
                key = f'{prefix}-{name}' if prefix else name
                if key not in posted:
                    posted[key] = getattr(instance, name)
            if args:
                args = (posted, *args[1:])
            else:
                kwargs['data'] = posted
        super().__init__(*args, **kwargs)
        autocomplete = dict(zip(ADDRESS_FIELDS, ('address-line1', 'address-line2', 'address-level2', 'address-level1', 'postal-code', 'country-name')))
        for name in ADDRESS_FIELDS:
            self.fields[name].widget.attrs['autocomplete'] = autocomplete[name]
        self.dealership = dealership
        self.matches = Customer.objects.none()
        if self.instance.pk:
            self.fields["revision"].required = True
            self.initial["revision"] = self.instance.revision
    @property
    def address_fields(self):
        return [self[name] for name in ADDRESS_FIELDS]

    @property
    def address_open(self):
        return any(self[name].errors or self[name].value() for name in ADDRESS_FIELDS)

    def clean(self):
        data = super().clean()
        for key in ("first_name", "last_name", "email", "phone", *ADDRESS_FIELDS):
            if key in data:
                data[key] = data[key].strip()
        for name in ADDRESS_FIELDS:
            if name in data and any(char in data[name] for char in ('\r', '\n')):
                self.add_error(name, 'Enter this address field on a single line.')
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

# SPDX-License-Identifier: MPL-2.0
from django import forms
from django.db.models import Q
from customers.forms import CustomerChoiceField
from customers.models import Customer
from inventory.models import Vehicle
from inventory.forms import VehicleChoiceField
from .models import DraftDeal, DraftFinanceProposal, MONEY_FIELDS, PROPOSAL_FIELDS
from .worksheet import draft_totals
from .tax_forms import configure_tax,clean_tax


def validate_worksheet(form, data):
    if all(data.get(name) is not None for name in MONEY_FIELDS):
        if draft_totals(data)["balance"] < 0:
            form.add_error(None, "Draft balance is below zero. Check the price, trade amounts, and planned down payment.")


def preserve_omitted_deal_type(args, instance):
    # Older draft forms may omit this newly added field. Never guess a cash sale.
    if args and args[0] is not None and "deal_type" not in args[0]:
        data = args[0].copy()
        data["deal_type"] = instance.deal_type
        return (data, *args[1:])
    return args


class DraftFinanceProposalForm(forms.ModelForm):
    class Meta:
        model = DraftFinanceProposal
        fields = PROPOSAL_FIELDS
        labels = {
            "interest_method": "Interest method",
            "creditor_name": "Proposed creditor / lender",
            "payment_frequency": "Payment frequency",
            "payment_count": "Number of payments",
            "annual_contract_rate": "Annual contract rate (%)",
            "first_payment_date": "First payment date",
            "illustration_finance_charge": "Precomputed finance charge (USD)",
        }
        help_texts = {
            "interest_method": "Match the proposed contract method.",
            "creditor_name": "Verify the legal entity before paperwork.",
            "payment_frequency": "Every 2 weeks and twice a month are different schedules.",
            "annual_contract_rate": "A contract rate is not the APR disclosure.",
        }
        widgets = {
            "payment_count": forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off"}),
            "annual_contract_rate": forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"}),
            "first_payment_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }

    def __init__(self, *args, read_only=False, **kwargs):
        if args and args[0] is not None:
            method_key = f"{kwargs.get('prefix')}-interest_method" if kwargs.get('prefix') else 'interest_method'
            if method_key not in args[0]:
                data = args[0].copy()
                data[method_key] = kwargs['instance'].interest_method
                args = (data, *args[1:])
        if args and args[0] is not None:
            charge_key=f"{kwargs.get('prefix')}-illustration_finance_charge" if kwargs.get("prefix") else "illustration_finance_charge"
            if charge_key not in args[0]:
                data=args[0].copy();data[charge_key]=kwargs["instance"].illustration_finance_charge;args=(data,*args[1:])
        super().__init__(*args, **kwargs)
        self.fields["illustration_finance_charge"].help_text="Supply the proposed total charge; it is not calculated from the contract rate."
        self.fields["illustration_finance_charge"].widget=forms.TextInput(attrs={"inputmode":"decimal"})
        self.order_fields(["interest_method","payment_frequency","payment_count","illustration_finance_charge","annual_contract_rate","first_payment_date","creditor_name"])
        self.fields["first_payment_date"].input_formats = ["%Y-%m-%d"]
        self.fields["payment_frequency"].choices = [("", "Not entered"), *DraftFinanceProposal.Frequency.choices]
        if read_only:
            for field in self.fields.values():
                field.disabled = True


class DraftWorksheetForm(forms.ModelForm):
    revision = forms.IntegerField(widget=forms.HiddenInput, min_value=1)

    class Meta:
        model = DraftDeal
        fields = ["deal_type", *MONEY_FIELDS, "notes"]
        labels = {
            "sale_price": "Vehicle price", "tax": "Sales tax",
            "title_registration": "Title & registration", "dealer_fee": "Dealer fee",
            "trade_allowance": "Trade allowance", "trade_payoff": "Trade payoff",
            "down_payment": "Planned down payment",
        }
        widgets = {"notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Notes for your team"})}

    def __init__(self, *args, read_only=False, **kwargs):
        self.original_data=args[0] if args and args[0] is not None else {}
        args = preserve_omitted_deal_type(args, kwargs["instance"])
        super().__init__(*args, **kwargs)
        self.fields["deal_type"].widget.attrs["data-deal-type"] = ""
        self.initial["revision"] = self.instance.revision
        for name in MONEY_FIELDS:
            self.fields[name].widget = forms.TextInput(attrs={"inputmode": "decimal", "data-money-field": name, "autocomplete": "off"})
        configure_tax(self)
        if read_only:
            for field in self.fields.values():
                field.disabled = True

    def clean(self):
        data = super().clean()
        clean_tax(self,data)
        validate_worksheet(self, data)
        return data

class DraftDealForm(forms.ModelForm):
    vehicle = VehicleChoiceField(queryset=Vehicle.objects.none(), label="Vehicle", empty_label="Choose a vehicle")
    submission_key = forms.UUIDField(
        widget=forms.HiddenInput,
        error_messages={
            "required": "We couldn't verify this form. Keep this page open and start a fresh deal in a new tab to copy your work.",
            "invalid": "We couldn't verify this form. Keep this page open and start a fresh deal in a new tab to copy your work.",
        },
    )
    buyer = CustomerChoiceField(queryset=Customer.objects.none(), required=False, label="Existing customer", empty_label="Choose a customer")
    co_buyer = CustomerChoiceField(queryset=Customer.objects.none(), required=False, label="Co-buyer (optional)", empty_label="No co-buyer")
    vehicle_mode = forms.ChoiceField(choices=[("existing","Choose from inventory"),("new","Add a vehicle")],widget=forms.RadioSelect,initial="existing",required=False,label="Vehicle")
    customer_mode = forms.ChoiceField(choices=[("existing", "Choose an existing customer"), ("new", "Add a new customer")], widget=forms.RadioSelect, initial="existing", label="Buyer")
    revision = forms.IntegerField(widget=forms.HiddenInput, min_value=1, required=False)
    class Meta:
        model = DraftDeal
        fields = ["deal_type", "vehicle", "buyer", "co_buyer", *MONEY_FIELDS, "notes"]
        labels = {"buyer": "Existing customer", "co_buyer": "Co-buyer (optional)", "tax": "Tax — manually entered", "title_registration": "Title / registration fees", "dealer_fee": "Dealer fee", "down_payment": "Planned down payment", "trade_payoff": "Trade payoff", "trade_allowance": "Trade allowance"}
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}
    def __init__(self, *args, dealership, **kwargs):
        self.original_data=args[0] if args and args[0] is not None else {}
        if kwargs.get("instance"):
            args = preserve_omitted_deal_type(args, kwargs["instance"])
        super().__init__(*args, **kwargs)
        self.fields["vehicle"].queryset = Vehicle.objects.filter(dealership=dealership).exclude(status=Vehicle.Status.SOLD)
        self.fields["vehicle"].empty_label = "Choose a vehicle"
        self.fields["vehicle"].required=False
        self.fields["deal_type"].widget.attrs["data-deal-type"]=""
        for name in MONEY_FIELDS:self.fields[name].widget=forms.TextInput(attrs={"inputmode":"decimal","data-money-field":name,"autocomplete":"off"})
        configure_tax(self,new=not bool(self.instance.pk))
        if self.instance.pk:
            self.fields.pop("submission_key")
            self.fields["vehicle"].queryset = Vehicle.objects.filter(dealership=dealership).filter(~Q(status="sold") | Q(pk=self.instance.vehicle_id))
            self.initial["revision"] = self.instance.revision
            self.fields["revision"].required = True
        else:
            self.initial["submission_key"] = self.instance.creation_key
        people = Customer.objects.filter(dealership=dealership)
        self.fields["buyer"].queryset = people
        self.fields["co_buyer"].queryset = people
        self.fields["buyer"].required = False
        if not self.is_bound and not people.exists():
            self.initial["customer_mode"] = "new"
    def clean(self):
        data = super().clean()
        if data.get("vehicle_mode")!="new" and not data.get("vehicle"):
            self.add_error("vehicle","Choose a vehicle, or select Add a vehicle.")
        if data.get("customer_mode") == "existing" and not data.get("buyer"):
            self.add_error("buyer", "Choose a customer, or select Add a new customer.")
        if data.get("buyer") and data.get("buyer") == data.get("co_buyer") and data.get("customer_mode") == "existing":
            self.add_error("co_buyer", "Buyer and co-buyer must be different people.")
        clean_tax(self,data)
        validate_worksheet(self, data)
        return data

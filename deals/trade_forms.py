# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from django import forms
from .models import DraftTradeIn, TRADE_FIELDS, TRADE_IDENTITY_FIELDS
from .worksheet import draft_totals


class TradeInForm(forms.ModelForm):
    revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    trade_allowance = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), label="Trade allowance")
    trade_payoff = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), label="Estimated payoff")

    class Meta:
        model = DraftTradeIn
        fields = TRADE_FIELDS
        labels = {"vin": "VIN", "lienholder_name": "Lienholder / payoff recipient", "payoff_good_through": "Payoff quote good through"}
        help_texts = {
            "vin": "As shown on ownership records. Historical VIN formats are supported.",
            "title_brand": "Keep Not verified until the title evidence is reviewed.",
            "odometer_status": "Reported information only; this is not a signed odometer disclosure.",
            "payoff_good_through": "Optional date from the quote; no payoff is sent or marked paid.",
            "notes": "Trade and title notes only. Do not enter account numbers, SSNs or banking details.",
        }
        widgets = {"notes": forms.Textarea(attrs={"rows": 3}), "payoff_good_through": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}

    def __init__(self, *args, deal, **kwargs):
        self.deal = deal
        super().__init__(*args, **kwargs)
        self.initial.update(revision=deal.revision, trade_allowance=deal.trade_allowance, trade_payoff=deal.trade_payoff)
        self.fields["payoff_good_through"].input_formats = ["%Y-%m-%d"]
        if self.instance.inventory_vehicle_id:
            for name in TRADE_IDENTITY_FIELDS:
                self.fields[name].disabled = True

    def clean_vin(self):
        return self.cleaned_data["vin"].strip().upper()

    def clean(self):
        data = super().clean()
        amounts = {name: getattr(self.deal, name) for name in ("sale_price", "tax", "title_registration", "dealer_fee", "down_payment")}
        if all(data.get(name) is not None for name in ("trade_allowance", "trade_payoff")):
            amounts.update({name: data[name] for name in ("trade_allowance", "trade_payoff")})
            if draft_totals(amounts)["balance"] < 0:
                self.add_error(None, "These trade amounts make the draft balance negative. Check the allowance, payoff and planned down payment.")
        return data


class TradeRemoveForm(forms.Form):
    revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    reason = forms.CharField(max_length=300, label="Reason for removing this trade")
    confirm = forms.BooleanField(label="Remove this trade and clear its allowance and estimated payoff from the draft.")


class TradeIntakeForm(forms.Form):
    revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    stock_number = forms.CharField(max_length=30)
    acquisition_cost = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), label="Inventory acquisition cost", help_text="Enter the reviewed cost. It is not automatically the allowance, payoff or trade equity.")
    title_received = forms.BooleanField(required=False, label="Title received")
    confirm = forms.BooleanField(label="I have checked acquisition and ownership evidence outside this draft and want to add this vehicle to inventory.")

    def clean_stock_number(self):
        return self.cleaned_data["stock_number"].strip().upper()

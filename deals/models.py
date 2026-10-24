# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from .worksheet import draft_totals
from inventory.identity import OdometerUnit, OdometerStatus, ODOMETER_FIELDS, validate_odometer
from inventory.models import Vehicle

MONEY_FIELDS = ("sale_price", "tax", "title_registration", "dealer_fee", "trade_allowance", "trade_payoff", "down_payment")
PROPOSAL_FIELDS = ("creditor_name", "payment_frequency", "payment_count", "annual_contract_rate", "first_payment_date")
TRADE_IDENTITY_FIELDS = ("vin", "year", "make", "model", "title_brand", *ODOMETER_FIELDS)
TRADE_FIELDS = (*TRADE_IDENTITY_FIELDS, "lienholder_name", "payoff_good_through", "notes")


class DealType(models.TextChoices):
    UNDECIDED = "undecided", "Not chosen"
    CASH = "cash", "Cash"
    OUTSIDE = "outside", "Outside financing"
    BHPH = "bhph", "Buy here, pay here"


FINANCING_TYPES = (DealType.OUTSIDE, DealType.BHPH)

def money_field():
    return models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0"))])

class DraftDeal(models.Model):
    deal_type = models.CharField(max_length=12, choices=DealType.choices, default=DealType.UNDECIDED)
    dealership = models.ForeignKey("core.Dealership", on_delete=models.PROTECT)
    creation_key = models.UUIDField(default=uuid.uuid4, editable=False)
    vehicle = models.ForeignKey("inventory.Vehicle", on_delete=models.PROTECT, related_name="draft_deals")
    buyer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="buyer_drafts")
    co_buyer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="co_buyer_drafts", blank=True, null=True)
    sale_price = money_field()
    tax = money_field()
    title_registration = money_field()
    dealer_fee = money_field()
    trade_allowance = money_field()
    trade_payoff = money_field()
    down_payment = money_field()
    notes = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-updated_at", "-pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(**{name+"__gte": 0 for name in MONEY_FIELDS}), name="draft_amounts_nonnegative"),
            models.CheckConstraint(condition=~models.Q(buyer=models.F("co_buyer")), name="draft_different_buyers"),
            models.UniqueConstraint(fields=["dealership", "creation_key"], name="draft_creation_key_per_dealer"),
            models.CheckConstraint(condition=models.Q(deal_type__in=DealType.values), name="draft_deal_type_known"),
        ]
    @property
    def draft_balance(self):
        return draft_totals({name: getattr(self, name) for name in MONEY_FIELDS})["balance"]
    def clean(self):
        super().clean()
        for name in ("vehicle", "buyer", "co_buyer"):
            related = getattr(self, name, None)
            if related and related.dealership_id != self.dealership_id:
                raise ValidationError({name: "Choose a record from this dealership."})
        if self.buyer_id and self.buyer_id == self.co_buyer_id:
            raise ValidationError({"co_buyer": "Buyer and co-buyer must be different people."})
        if self.pk and self.vehicle_id:
            for trade in self.trades.filter(archived_at__isnull=True):
                if trade.inventory_vehicle_id == self.vehicle_id or (trade.vin and self.vehicle.vin and trade.vin.upper() == self.vehicle.vin.upper()):
                    raise ValidationError({"vehicle": "The vehicle being sold cannot also be this deal's active trade-in."})


class DraftFinanceProposal(models.Model):
    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Weekly"
        BIWEEKLY = "biweekly", "Every 2 weeks"
        SEMIMONTHLY = "semimonthly", "Twice a month"
        MONTHLY = "monthly", "Monthly"

    deal = models.ForeignKey(DraftDeal, on_delete=models.PROTECT, related_name="finance_proposals")
    kind = models.CharField(max_length=12, choices=[(kind, DealType(kind).label) for kind in FINANCING_TYPES])
    creditor_name = models.CharField(max_length=120, blank=True)
    payment_frequency = models.CharField(max_length=12, choices=Frequency.choices, blank=True)
    payment_count = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    annual_contract_rate = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    first_payment_date = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind"]
        constraints = [
            models.UniqueConstraint(fields=["deal", "kind"], name="one_proposal_per_draft_kind"),
            models.CheckConstraint(condition=models.Q(kind__in=FINANCING_TYPES), name="proposal_kind_financing"),
            models.CheckConstraint(condition=models.Q(payment_count__isnull=True) | models.Q(payment_count__gte=1), name="proposal_payment_count_positive"),
            models.CheckConstraint(condition=models.Q(annual_contract_rate__isnull=True) | models.Q(annual_contract_rate__gte=0), name="proposal_rate_nonnegative"),
            models.CheckConstraint(condition=models.Q(payment_frequency="") | models.Q(payment_frequency__in=("weekly", "biweekly", "semimonthly", "monthly")), name="proposal_frequency_known"),
        ]

class DraftTradeIn(models.Model):
    deal = models.ForeignKey(DraftDeal, on_delete=models.PROTECT, related_name="trades")
    vin = models.CharField(max_length=30, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1886)])
    make = models.CharField(max_length=60, blank=True)
    model = models.CharField(max_length=80, blank=True)
    title_brand = models.CharField(max_length=15, choices=Vehicle.Brand.choices, default=Vehicle.Brand.UNKNOWN)
    odometer_reading = models.PositiveIntegerField(null=True, blank=True)
    odometer_unit = models.CharField(max_length=10, choices=OdometerUnit.choices, default=OdometerUnit.UNKNOWN)
    odometer_status = models.CharField(max_length=12, choices=OdometerStatus.choices, default=OdometerStatus.UNKNOWN)
    lienholder_name = models.CharField(max_length=120, blank=True)
    payoff_good_through = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    inventory_vehicle = models.OneToOneField(Vehicle, on_delete=models.PROTECT, null=True, blank=True, related_name="source_trade")
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["pk"]
        constraints = [models.UniqueConstraint(fields=["deal"], condition=models.Q(archived_at__isnull=True), name="one_active_trade_per_draft")]

    def __str__(self):
        return " ".join(str(value) for value in (self.year, self.make, self.model) if value) or self.vin or "Trade-in vehicle"

    def clean(self):
        super().clean()
        validate_odometer(self)
        errors = {}
        if not self.vin and not (self.year and self.make and self.model):
            errors["vin"] = "Enter the VIN, or the year, make and model to identify this trade."
        if self.deal_id:
            sale_vehicle = self.deal.vehicle
            if self.vin and sale_vehicle.vin and self.vin.upper() == sale_vehicle.vin.upper():
                errors["vin"] = "The trade-in cannot be the same vehicle being sold."
            if self.inventory_vehicle_id and self.inventory_vehicle.dealership_id != self.deal.dealership_id:
                errors["inventory_vehicle"] = "Choose inventory from this dealership."
        if errors:
            raise ValidationError(errors)


class DealEvent(models.Model):
    deal = models.ForeignKey(DraftDeal, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at", "-pk"]

# SPDX-License-Identifier: MPL-2.0
from core.filtering import FilterField as Field, FilterSchema
from inventory.models import Vehicle
from .models import DealType

SCHEMA = FilterSchema(
    resource="deals", title="Draft deals", route="deals", search_hint="Customer, stock number, VIN, vehicle or draft #",
    fields=(Field("type", "Deal type", "deal_type", "choice", tuple(DealType.choices)), Field("price", "Vehicle price", "sale_price", "decimal"), Field("down", "Planned down payment", "down_payment", "decimal"), Field("make", "Vehicle make", "vehicle__make"), Field("brand", "Vehicle title brand", "vehicle__title_brand", "choice", tuple(Vehicle.Brand.choices)), Field("buyer", "Buyer last name", "buyer__last_name"), Field("notes", "Notes", "notes"), Field("updated", "Last saved", "updated_at__date", "date")),
    sorts={"recent": ("Recently saved", ("-updated_at", "-pk")), "price_low": ("Lowest price", ("sale_price", "pk")), "price_high": ("Highest price", ("-sale_price", "pk")), "oldest": ("Oldest drafts", ("created_at", "pk"))},
)

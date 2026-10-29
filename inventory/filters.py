# SPDX-License-Identifier: MPL-2.0
from core.filtering import FilterField as Field, FilterSchema
from .models import Vehicle

SCHEMA = FilterSchema(
    resource="inventory", title="Vehicles", route="inventory",
    search_hint="Stock number, VIN, year, make or model",
    fields=(
        Field("status", "Status", "status", "choice", tuple(Vehicle.Status.choices)),
        Field("brand", "Title brand", "title_brand", "choice", tuple(Vehicle.Brand.choices)),
        Field("title_received", "Title received", "title_received", "boolean"),
        Field("make", "Make", "make"), Field("model", "Model", "model"),
        Field("year", "Model year", "year", "integer"),
        Field("stock", "Stock number", "stock_number"), Field("vin", "VIN", "vin"),
        Field("cost", "Total investment", "filter_total_cost", "decimal"),
        Field("photos", "Has photos", "filter_has_photos", "boolean"),
        Field("updated", "Last updated", "updated_at__date", "date"),
    ),
    sorts={"recent": ("Recently updated", ("-updated_at", "-pk")), "year_new": ("Newest model year", ("-year", "make", "model", "pk")), "year_old": ("Oldest model year", ("year", "make", "model", "pk")), "name": ("Make and model", ("make", "model", "year", "pk")), "cost_low": ("Lowest investment", ("filter_total_cost", "pk")), "cost_high": ("Highest investment", ("-filter_total_cost", "pk"))},
    extras={"scope": ("active", "missing-title", "attention"), "status": tuple(Vehicle.Status.values)},
)

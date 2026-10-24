# SPDX-License-Identifier: MPL-2.0
from core.filtering import FilterField as Field, FilterSchema

SCHEMA = FilterSchema(
    resource="customers", title="Customers", route="customers", default_sort="name",
    search_hint="Name, phone or email",
    fields=(Field("first_name", "First name", "first_name"), Field("last_name", "Last name", "last_name"), Field("email", "Email", "email"), Field("phone", "Phone digits", "phone_normalized"), Field("updated", "Last updated", "updated_at__date", "date")),
    sorts={"name": ("Name A–Z", ("last_name", "first_name", "pk")), "recent": ("Recently updated", ("-updated_at", "-pk")), "oldest": ("Oldest records", ("created_at", "pk"))},
)

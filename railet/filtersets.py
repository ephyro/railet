# SPDX-License-Identifier: MPL-2.0
# Composition registry: each module owns its filter fields and ordering choices.
from inventory.filters import SCHEMA as inventory
from customers.filters import SCHEMA as customers
from deals.filters import SCHEMA as deals
from finance.filters import SCHEMA as accounts

SCHEMAS = {schema.resource: schema for schema in (inventory, customers, deals, accounts)}

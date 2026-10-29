# SPDX-License-Identifier: MPL-2.0
from core.filtering import FilterField as Field, FilterSchema

SCHEMA = FilterSchema(
    resource='accounts', title='Customer accounts', route='ledger_demo_list',
    search_hint='Customer, phone, account #, stock number or VIN',
    enabled_setting='DEMO_LEDGER_ENABLED',
    fields=(
        Field('linked', 'Draft context linked', 'has_context', 'boolean'),
        Field('customer', 'Customer first name', 'customer__first_name'),
        Field('last_name', 'Customer last name', 'customer__last_name'),
        Field('stock', 'Stock number as linked', 'account_context__snapshot__stock_number'),
        Field('vin', 'VIN as linked', 'account_context__snapshot__vin'),
        Field('method', 'Proposed interest method as linked', 'account_context__snapshot__proposed_terms__interest_method', 'choice', (('precomputed','Precomputed'),('simple','Simple interest'))),
        Field('frequency', 'Proposed frequency as linked', 'account_context__snapshot__proposed_terms__payment_frequency', 'choice', (('monthly','Monthly'),('weekly','Weekly'),('biweekly','Every two weeks'),('semimonthly','Twice a month'))),
        Field('opening', 'Opening date', 'opening_on', 'date'),
    ),
    sorts={'recent': ('Newest accounts', ('-created_at','-pk')),
           'customer': ('Customer A–Z', ('customer__last_name','customer__first_name','pk')),
           'opening': ('Earliest opening date', ('opening_on','pk')),
           'oldest_due': ('Oldest overdue first', ('pk',))},
    extras={'scope': ('linked','unlinked'),'status':('past_due','due_today','current','uncalculated')},
)

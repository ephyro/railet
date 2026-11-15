# Finding BHPH demo accounts

The BHPH account list uses Railet's shared typed-filter and private saved-view system behind `DEMO_LEDGER_ENABLED`. When `DEMO_SERVICING_ENABLED` is also set, eligible accounts can show **simulated** due amounts, statuses and next unpaid dates from an explicitly selected demo schedule. These are not live servicing, actual delinquency decisions or payoff calculations; receipts remain unapplied in the ledger. See [demo servicing](DEMO_SERVICING.md).

## Everyday workflow

Search for the customer's current name, phone or email, the account label, or the vehicle description, stock number or VIN saved when draft context was linked. Multiple words must each match a supported field. `#123` selects exactly account 123; a bare numeric search can also match phone digits. Oversized numeric IDs are ignored safely rather than sent to the database as an overflowing integer.

The list identifies the customer, account number and saved vehicle before opening the account. Quick scopes distinguish all accounts, accounts linked to a draft and accounts needing context. Changing scope preserves the search and advanced rules; filters are not silently discarded. A no-match state offers a reset rather than suggesting another customer's account.

Advanced rules support linked/unlinked context, customer names, recorded stock/VIN, proposed interest method and frequency as linked, and opening date. Sort by newest account, customer or opening date. With demo servicing enabled, status scopes and oldest-overdue ordering are also available; those worklist searches are bounded to 500 matching accounts and fail closed when too broad. The list also displays the latest recorded receipt and whether it was corrected. Rules are allowlisted and typed; invalid rules hide results with actionable errors. No arbitrary ORM lookup or dealership selector is exposed.

## Module and security boundaries

Finance owns the schema and account search query. Core owns parsing, the filter UI and saved preferences. The composition registry now includes accounts; an optional schema-level `enabled_setting` also gates saved-view creation for development-only lists. Existing inventory, customer and deal schemas remain available without a new setting. Owners, staff and viewers can save their own search preferences; that permission never grants financial write access.

Queries begin with books and customers authorized for the user's dealership, before applying any OR or advanced conditions. Vehicle identity searches use immutable linked snapshots, not today's inventory values. Contact searches use the canonical current customer profile. Pagination retains the complete filter state. Saved views store search settings, not result sets; they remain scoped to their owner and dealership and are reevaluated each time.

The account list remains private/no-store. No money is posted or reallocated, no synthetic data is copied to production, and no live gate changes. Searches can contain sensitive identifiers when real data is eventually approved; production request/analytics logging must continue to exclude query values under the broader customer-information controls.

No new library, service or microservice was introduced. Database indexing beyond existing keys and the linked-snapshot relationships should be driven by measured account volumes; synthetic developer checks are not a production load test or dealership staff validation.


Account-search verification (October 26, 2026): the full PostgreSQL suite passed 293 tests in 113.799 seconds with no skips; 25 focused PostgreSQL checks and eight focused SQLite checks passed. Browser checks exercised stock search, linked/unlinked scopes, advanced-rule editing, private saved views and account navigation at 1440/390/320 pixels without page overflow. These are synthetic developer checks; no production workload or staff validation is claimed. Private evidence: `.local/account-search-review/`.

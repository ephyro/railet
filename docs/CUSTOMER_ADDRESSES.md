# Shared customer contact addresses

Customers now own optional structured contact-address fields: street lines 1/2, city, state/region, postal code and country. Existing records migrate to blank/unknown address values without changing names, contact information, revisions or retained event history. No state or country is guessed.

## Entry and reuse

Quick customer creation still requires only the existing name fields. The shared customer form, including inline creation inside a draft, puts address fields behind **Contact address (optional)**. The section opens when it contains values or validation errors. Inputs are labeled and use browser address-autocomplete tokens; entered work is retained after errors and revision conflicts.

Address components support international text without assuming US-only state codes or postal formats. Length and single-line validation are structural controls, not postal verification. Partial addresses are allowed; their presence never marks a record legally complete or verified. An address does not establish residence, ownership, tax jurisdiction or permission to contact the customer. No geocoding, mailing, address-validation provider or automated communication was added.

Current contact addresses are reused in customer details, buyer/co-buyer deal review and the BHPH workspace. `customers.records.address_snapshot` is the explicit read interface for document/export consumers. There is one authoritative customer record rather than duplicate account/deal addresses.

Older submissions that omit new address fields preserve existing values; explicit blank submissions clear the specified fields. Prefixed and keyword-bound forms follow the same rule. Saving uses the existing dealership authorization, revision-conflict protection and customer event trail. No new permission to edit another dealership's profile is granted.

## Historical documents and portability

New demo packets use **demo-summary-v4**, snapshot schema 4. Buyer and co-buyer addresses appear in the captured-facts preview and saved HTML. Addresses are frozen into structured data and display lines at creation. Later customer edits do not rewrite retained packet bytes, template versions or hashes. Changing an address after preview requires a fresh preview. Older packets keep their original content, including those saved before address fields existed.

Account export format **demo-account-export-v2** adds a structured address under `current_customer`. That is current contact information captured at download time, distinct from frozen draft context. Earlier export audit records keep their existing version metadata. This remains a private one-account export, not a full dealership backup. The address is included in the reviewed private-data scope before downloading.

No live contract, transaction or regulatory readiness gate is enabled. Applicable document/address requirements still require the workflow-specific research and review in RAILET_PLAN.md. Developer checks are not postal, staff or legal validation.


Customer-address verification (October 26, 2026): the final PostgreSQL suite passed 324 tests in 112.813 seconds without skips. Focused checks cover optional/partial entry, international text, omitted-field compatibility, explicit clearing, revision conflicts, authorization, escaped display, existing-data migration, visible packet previews, frozen buyer/co-buyer addresses and versioned account exports. Twenty-three SQLite address/snapshot checks and nine SQLite address/migration checks passed. Browser checks confirmed canonical reuse, preservation of old packet addresses after a later edit and 1440/390/320-pixel layouts. An outdated historical migration-test target was corrected before the successful final run. These are synthetic developer checks, not staff, postal or legal validation. Private evidence: `.local/customer-address-review/`.

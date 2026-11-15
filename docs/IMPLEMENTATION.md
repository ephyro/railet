# Initial inventory implementation

Historical notes from the first slice. Source review on November 13, 2026 compared settings, requirements, inventory audit migration `core.0008_inventory_audit_guards` and current module boundaries; no runtime checks were repeated. For current features and checks, see [DEVELOPMENT.md](DEVELOPMENT.md) and the module documentation linked there.

The first slice covered inventory, not the entire Phase 1 roadmap. Subsequent synthetic development added customer profiles, draft deals, private uploads, local feedback, demo packet summaries and a synthetic financial ledger. An isolated MFA experiment exists but is not connected to login. Live document generation/signing, production MFA, live servicing, production hosting and provider integrations remain gated. See [customers and deals](CUSTOMERS_AND_DEALS.md) and [remaining work](REMAINING_WORK.md).

Django 5.2 LTS was selected for its maintenance window and Python compatibility. Requirement ranges must be resolved and locked in a network-enabled environment before release. PostgreSQL is the intended database; SQLite is an explicit local-only fallback. No production release is authorized by this scaffold.

UI uses original server-rendered templates and local CSS. HTMX and Tailwind tooling are deliberately deferred rather than loading third-party scripts/CDNs merely for the scaffold.

Audit events capture changes in the same transaction as writes. PostgreSQL row locks serialize edits; form revision tokens reject stale edits with HTTP 409 while preserving submitted fields for comparison. Subsequent isolated synthetic PostgreSQL checks exercised concurrency; multi-user production security and operational verification remain open. Current inventory audit migration `core.0008_inventory_audit_guards` rejects audit updates/deletes and new mismatched dealership/vehicle inserts on SQLite/PostgreSQL, and prevents changing an audited vehicle's dealership. Existing installations must apply it; historical mismatches are not repaired. Privileged mutation, disabled guards and PostgreSQL `TRUNCATE` remain outside those row-level protections. This is not a claim that every module's audit history has identical guards.

Title brands are an initial single primary-status vocabulary, not a complete representation of combined brands or legal disclosure applicability. Document evidence and multi-brand support must precede live paperwork. Costs are inventory estimates, not accounting ledger postings.

Historical verification on October 23, 2026: the Ubuntu development VM successfully built the application image, applied the migrations then present, passed Django system checks and migration drift checks, and passed all 13 application tests then present against PostgreSQL. An actual CSRF-protected demo login, authenticated dashboard, and synthetic inventory returned HTTP 200 through the SSH tunnel. These were developer checks, not staff usability validation. A later [synthetic database-and-private-file restore exercise](SYNTHETIC_RESTORE_EXERCISE.md) does not establish production recovery; staging HTTPS remains unverified.

Sources: https://docs.djangoproject.com/en/5.2/releases/5.2/ ; https://www.djangoproject.com/download/

Inventory follow-up: revision conflict detection, accessible form error summary, unsaved-change warning, and regression tests added. Host dependency installation was unavailable initially; runtime validation subsequently succeeded inside the development VM.

# Initial inventory implementation

Historical notes from the first slice. For current features and checks, see [DEVELOPMENT.md](DEVELOPMENT.md) and the module documentation linked there.

The first slice is inventory, not the entire Phase 1 roadmap. Customer profiles and draft deals are now implemented; uploads, MFA, feedback submission, document generation, financial ledger, production hosting and integrations remain unimplemented. See CUSTOMERS_AND_DEALS.md.

Django 5.2 LTS was selected for its maintenance window and Python compatibility. Requirement ranges must be resolved and locked in a network-enabled environment before release. PostgreSQL is the intended database; SQLite is an explicit local-only fallback. No production release is authorized by this scaffold.

UI uses original server-rendered templates and local CSS. HTMX and Tailwind tooling are deliberately deferred rather than loading third-party scripts/CDNs merely for the scaffold.

Audit events capture changes in the same transaction as writes. PostgreSQL row locks serialize edits; form revision tokens reject stale edits with HTTP 409 while preserving submitted fields for comparison. This still needs PostgreSQL runtime verification before multi-user production use. Audit records are not protected from privileged direct database mutation.

Title brands are an initial single primary-status vocabulary, not a complete representation of combined brands or legal disclosure applicability. Document evidence and multi-brand support must precede live paperwork. Costs are inventory estimates, not accounting ledger postings.

Verification on October 23, 2026: the Ubuntu development VM successfully built the application image, applied all migrations, passed Django system checks and migration drift checks, and passed all 13 application tests against PostgreSQL. An actual CSRF-protected demo login, authenticated dashboard, and synthetic inventory returned HTTP 200 through the SSH tunnel. These are developer checks, not staff usability validation. Staging HTTPS and backup restoration remain unverified.

Sources: https://docs.djangoproject.com/en/5.2/releases/5.2/ ; https://www.djangoproject.com/download/

Inventory follow-up: revision conflict detection, accessible form error summary, unsaved-change warning, and regression tests added. Host dependency installation was unavailable initially; runtime validation subsequently succeeded inside the development VM.

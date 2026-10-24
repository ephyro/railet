<!-- SPDX-License-Identifier: MPL-2.0 -->
# Overseer review — October 24, 2026

Disposition: accept the corrected saved-draft review for synthetic development.
No production, live-customer, payment, signing or legal-compliance approval is given.

## Implementation handoff

The implementation agent owned five new review files. Its first handoff was
returned for corrections: sidebar CSS inheritance, explicit private/no-store cache
headers, financing links to the actual proposal editor and consistent parent/child
financial reads. The overseer integrated the route and workspace navigation and
removed the temporary test-only URL registration. No existing financial model,
migration, license boundary or production gate changed.

Independent evidence: 114 PostgreSQL tests passed; 13 focused SQLite review tests
passed; system and migration-drift checks passed. Firefox checked real keyboard
navigation, unknown/zero handling, exact trade amounts, active financing selection,
cache headers, CSRF-valid POST denial, five viewport widths and long/large values.
See DEAL_REVIEW.md for details. Existing source changes were compared against a
source-only baseline and matched the overseer's intended integration/documentation
files. This is developer verification, not dealership staff usability testing.

## Independent audit disposition

The local model reviewed the existing trade/intake workflow and returned one
concrete observation plus two unverified concerns. Its report was treated as
input to the overseer's assessment, not as a safety sign-off.

1. **Duplicate VINs through ordinary inventory entry — confirmed known limit.**
   The overseer reproduced an authorized staff POST creating a second stock record
   with the same dealership/VIN in an ephemeral test database. The same request
   from a viewer was rejected with HTTP 403. Trade intake has its own duplicate
   check; ordinary inventory does not guarantee VIN uniqueness, as already recorded
   in TRADE_INS.md. This can mislead stock/cost reporting and needs resolution
   before a live inventory pilot. It is not an authorization bypass or proof of a
   live financial posting. The auditor's High classification is not accepted as
   an established security severity. A universal VIN unique constraint was not
   added: reacquisition, sold stock history, legacy identifiers and existing-data
   reconciliation need an explicit inventory identity policy first.
2. **VIN-less trade may represent the sale vehicle — not established as a defect.**
   Year/make/model alone cannot establish that two records are the same physical
   vehicle. Unknown identity is allowed in a draft; inventory intake requires a
   VIN and known identity fields. Known matching sale/trade VINs and matching
   linked inventory IDs are rejected. Do not invent a uniqueness rule over
   year/make/model or claim an unknown identity is verified.
3. **In-view POST checks instead of decorators — no functional defect established.**
   Existing mutations are POST-gated, authenticated, role/tenant-scoped and
   CSRF-protected. GET non-mutation and denied CSRF checks are covered by tests.
   The choice of decorator versus equivalent in-view checks is not itself a
   security failure.

The two duplicate-VIN diagnostic cases passed as observations of existing behavior;
they are private test probes, not permanent tests endorsing duplicate stock.
No real customer or inventory data was imported or edited for this assessment.

## Outstanding gates

Resolve inventory identity/reacquisition and duplicate-reconciliation policy before
production inventory acceptance. Legal forms, title/odometer transfer evidence,
finance calculations, servicing, retention/restore and security gates in the product
plan remain open. Passing tests and a read-only review page do not close them.

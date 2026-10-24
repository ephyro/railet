<!-- SPDX-License-Identifier: MPL-2.0 -->
# Saved draft review

`/deals/<id>/review/` presents current saved records for internal human review.
The deal workspace's Review deal link opens it; leaving unsaved worksheet edits
still uses the existing unsaved-work warning. Owners and staff receive edit links;
viewers receive links to readable records.

The page shows canonical vehicle, buyer/co-buyer contact, reported title/mileage,
worksheet amounts, active trade details and only the proposal matching the chosen
financing type. Blank is distinct from zero. Existing Decimal worksheet arithmetic
is reused; no tax, interest, APR or payment schedule is calculated. The worksheet
balance remains a draft estimate rather than a statutory amount-financed disclosure.

Completeness reminders identify blank or explicitly unverified stored facts. They
are not a statutory checklist, evidence verification or a legal readiness decision.
A filled field is not automatically verified. Final paperwork and legal/financial
verification remain unavailable. Existing compliance and production gates in
RAILET_PLAN.md, DEAL_TYPES_AND_TERMS.md and TRADE_INS.md are unchanged. No new
regulatory rule, document template or production permission is introduced.

The page accepts GET/HEAD only, requires dealership membership and scopes the
parent on the server. Invalid cross-dealership vehicle/customer links fail closed;
a foreign linked inventory record is not exposed. Response caching is explicitly
private/no-store. The short read transaction locks only the parent deal row while
loading its child trade/proposal data and rendering, using PostgreSQL `OF self` to
avoid locking nullable joined co-buyers. Existing draft writers lock the same row,
so their child/money updates cannot interleave with this read. No review status,
financial entry, loan, contract, signature or finalized artifact is created.
This is a current-record view, not an immutable generated-document snapshot.

## Verification and agent handoff review

October 24, 2026: implementation was delegated to an existing GPT-6 Luna TTY agent
under a five-file ownership boundary. The overseer reviewed the first handoff and
returned corrections for a global-sidebar CSS collision, missing sensitive-page
cache controls, financing links targeting the wrong editor and consistency of
multi-query financial reads. Title-received follow-up was also added. The revised
handoff was checked independently before development acceptance.

The temporary test-only URL registration was removed during integration so tests
exercise the actual application route. Independent checks passed:

- All 114 PostgreSQL tests, including the existing trade and concurrency suites.
- All 13 focused review tests on local SQLite; Django checks and migration-drift
  check passed with no new models or migrations.
- Firefox keyboard entry from the workspace; correct cash/trade and BHPH/zero-rate
  displays; correct financing editor links; private/no-store response headers;
  an authenticated CSRF-valid POST rejected with HTTP 405.
- Layouts at 1440, 1024, 768, 390 and 320 pixels, including a full-width notice,
  long identity text and large monetary values without horizontal page overflow.

Browser checks used existing synthetic deals #8 and #7 without editing them.
These are developer checks, not staff usability validation or legal review.
Acceptance is for synthetic development; production approval is not granted.

The overseer's final screenshot review also caught a narrow-screen currency line
break. The CSS now lets the label and balance occupy separate lines while keeping
the entire currency value intact. Firefox responsive checks were rerun successfully.

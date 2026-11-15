# Frozen completion rehearsals

Implemented October 30, 2026. Community MPL 2.0, development and synthetic data
only. This is a terminal internal review exercise, not deal finalization, a real
sale, reviewed paperwork, a contract, signature, loan, receivable, tax filing or
payment. The legal/financial production gates in RAILET_PLAN.md remain in force.

## Workflow

From a saved deal, choose **Review deal**, then **Review and freeze**. The preview
shows the saved vehicle and buyers, worksheet figures, selected financing terms,
active trade, and remaining completeness reminders. Correction links return to the
existing review/editor. Missing deal type, nonpositive price, negative balance,
archived/sold source state, stale/unsupported tax data, or missing/invalid selected
financing terms block this narrow rehearsal. These are internal workflow rules,
not an exhaustive legal checklist or evidence that an entered fact is verified.

Existing reminders about title, mileage, contact or trade evidence remain visible.
If reminders remain, a review note is required and frozen alongside them. The
reviewer must confirm the saved facts and the rehearsal-only consequences.
Acknowledgement does not verify evidence, satisfy a disclosure, waive a requirement,
or turn an unknown fact into a reassuring value.

Confirmation creates a Documents-owned demo packet and one immutable completion
record, appends a deal history event, and moves the deal out of In progress into
**Completed rehearsals**. Completed rows and detail views show frozen buyer/vehicle
names. Text search also matches frozen names and vehicle identities after shared
profiles change. Existing advanced buyer/vehicle filters still refer to current
canonical records; this worklist is not a historical accounting report. The completion page exposes the retained HTML summary, source revision,
actor/time, original deal/trade notes, review notes, reminders and supporting-file references. Links to current
profiles/files are explicitly identified. No vehicle status or customer balance
changes; no contract or BHPH account is created.

Worksheet/party/financing/trade changes and archive/restore are blocked afterwards.
Shared customer/vehicle profiles, operational follow-ups and supporting-file
lifecycle remain independent; their later changes do not rewrite the completion.
A completion with no linked BHPH account can be marked with a separate, immutable
synthetic void rehearsal (`/deals/<id>/completion/void/`, `DemoCompletionVoid`).
This requires a signed 30-minute preview, a reason, and explicit confirmation,
and is rejected if any `DemoAccountContext` is linked to the deal (even when the
ledger demo gate is off). A void rehearsal does not cancel any sale or contract
or correct a payment or balance, and blocks later synthetic account opening or
linking. The original completion and packet remain unchanged. There is no reopen
or amend feature; account-linked corrections remain unresolved. A reviewed,
independent synthetic follow-on draft can be created from the voided rehearsal
as described below. A future live
amendment/cancellation workflow needs separate requirements, authorization,
reviewed documents and financial reconciliation.

Existing synthetic BHPH accounts stay accessible, including from the completion
page (which notes that an account opened from an earlier draft before the
rehearsal may have saved context preceding the frozen completion). A new
synthetic account can be opened from a verified non-voided frozen completion;
an existing unlinked account for the same customer can also be linked after a
preview of the frozen facts (`link_completed`). This does not restrict
payment/reversal rehearsal on an existing book, and a successful original
opening can still be retried.

## Capture, concurrency and integrity

- Membership scopes all routes. Owners/inventory staff can prepare/confirm;
  read-only members can inspect a completed record. Writes require CSRF protection.
- Both DEBUG-derived DEMO_COMPLETION_ENABLED and DEMO_PACKETS_ENABLED must be on.
  No live behavior is enabled by a completed rehearsal.
- Preview locks dealership, parent deal, vehicle, and canonical customers in a
  consistent order. Parent locking coordinates proposal/trade/file writers.
- A signed 30-minute token binds actor, dealership, deal, random request key and
  review digest. The digest covers the frozen packet facts plus related revisions,
  vehicle state and active supporting-file manifest (up to 500 references).
- The service captures and checks the same facts under locks at confirmation.
  Changes require a new preview; entered review notes remain and both confirmation
  checkboxes clear. Duplicate successful requests return one completion; competing
  keys cannot complete a deal twice. The Documents packet creation interface now
  takes dealership before membership, matching this shared lock order.
- A completion, its Documents packet and history event commit in one transaction.
  An audit failure rolls them back together. No financial posting occurs.
- The completion references the exact packet, source and artifact hashes and
  retains the review digest/metadata. Reads verify stored snapshot and HTML bytes;
  integrity failures return HTTP 409 rather than rebuilding from current records.
- PostgreSQL/SQLite guards prohibit completion changes/deletion, changes to its
  packet, parent/child fact edits and rewrites of the completed deal's history.
  Child inserts/reparenting are also blocked. A completion insert checks packet,
  deal, revision and actor scope. PostgreSQL guards lock the parent to serialize
  source writes with completion. Privileged database administrators remain able
  to change schema/disable guards; this is not a claim of external certification.
- File references retain title, record ID, SHA-256 and byte length as captured.
  No upload is independently verified/scanned here and no original file is
  overwritten or deleted. Subsequent archival does not rewrite the manifest.
- Completion does not alter old packets, contract templates, tax calculations,
  calculation versions, previously recorded receipts, or principal balances.

## Production and review boundaries

No new legal determination is implemented. Existing primary-source research and
unresolved applicability/effective-date/professional-review gates in the product
plan, Florida draft tax register, deal types/terms, title/trade and Documents notes
continue to apply. Before live finalization, separately review legal forms and
applicability, disclosures/signatures/delivery, lending calculations, transaction
states, inventory sale/reservation/reacquisition rules, corrections and retention.
The internal checklist is not that review. No retention/deletion policy changes.

## Verification

Reference cash case: $12,000.25 price + $700.00 tax + $99.75 fee − $1,000.00 planned
down = $11,800.00 frozen estimate. Browser reference: $12,500.25 + $800.00 tax +
$200.00 title fees + $99.75 dealer fee − $2,000.00 = $11,600.00. Both remain worksheet
estimates. Developer tests cover scope/roles/CSRF/gates, blockers, required notes,
zero financing values, stale source/file changes, retries, frozen historical
identities, tamper detection, raw database guards and full audit rollback.
PostgreSQL races test duplicate/distinct confirmations and edits racing completion.
These are developer checks, not staff acceptance, legal review or live approval.

Final developer verification, October 30, 2026: all 453 PostgreSQL regression
tests passed with the final integrated source, including three completion race
cases. The targeted review/lifecycle/packet/account suite passed 72 checks; the
SQLite completion suite passed 18. Django system and migration drift checks
passed. New migrations were applied to the isolated synthetic preview. Browser
checks saved a $11,600.00 rehearsal, confirmed unchanged inventory/book counts,
retained frozen identities after shared-profile edits, exercised edit redirects
and the completed list, and showed actionable blockers for a separate incomplete
draft. Final read-only checks verified original-name search and sequential figure
rows at 1440, 390 and 320 pixels without outer horizontal overflow. Captures and
fixture IDs remain local, ignored artifacts. Staff usability validation, legal
review and live production acceptance remain outstanding.

## Completed rehearsal to synthetic account handoff

A completed BHPH rehearsal can start a new synthetic account through its frozen
record. The user enters an invented opening amount and reviews it separately; it
is never inferred from the deal balance. The saved completion packet is verified,
its frozen financing display is compared with database-frozen structured proposal
fields, and the account context records the completion identifier and digest.
The frozen buyer name and vehicle are preserved even if shared profiles change.
Account screens label current contact details and the name captured at completion.
The opening and context are committed atomically, use the existing balanced demo
ledger and request-key retry checks, and still create no live loan or payment.
An existing unlinked synthetic account can also attach the verified completed
rehearsal after an explicit preview. The link requires the same dealership and
customer and preserves the frozen snapshot and existing ledger entries. SQLite
checks passed (two PostgreSQL-only concurrency tests skipped); all 22 focused
PostgreSQL tests passed, including concurrent link attempts. Privileged schema
changes can bypass database guards; production and review gates remain.

Independent Argon review identified retry-integrity and labeling concerns, which
were addressed. Developer verification: 27 focused PostgreSQL tests passed,
including a synthetic payment after opening; 17 focused SQLite tests passed.
SQLite migration 0014 restores account-context immutability and scoped insertion
checks lost during an earlier SQLite table rebuild. This is not staff validation.


## Synthetic follow-on draft from a void rehearsal

An owner or staff member can review and create one separate draft from a verified
voided completion, provided no account is linked. A signed, actor/dealer-bound
30-minute preview, explicit confirmation and reason precede creation. The service
locks the dealership, completed deal, vehicle and customers; changed revisions
or sold status require a fresh review or block creation. Retries with the same
key and facts return the same draft; competing requests cannot create duplicates.

The new draft links the current shared parties/vehicle while preserving the
source completion, packet, hashes, void and actor/reason in immutable provenance
and the new deal's creation history. Supported, verified frozen worksheet values
are draft estimates; unsupported or stale tax and any trade adjustment result in
zero figures with a preview notice. Financing proposals, trade details, documents
and follow-ups are not copied; review and enter them separately. No documents,
account or ledger postings are created or changed. The new draft remains editable
and does not modify the voided source. Owner exports include the provenance.

This requires DEBUG and both synthetic completion/packet gates. It is not a legal
amendment, cancellation, sale, payment or readiness determination; legal and
financial review remains open. The development tests are not staff validation.

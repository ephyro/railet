# Portable synthetic account export

The BHPH workspace now links to **Export account records**, with a clear review of included private information and a deliberate **Download demo account ZIP** action. This is a community feature. It is gated by the existing synthetic-ledger setting and does not enable any live servicing behavior.

## Contents and financial meaning

- `account.json`: account identifiers and opening provenance, current canonical customer contact information, frozen linked draft context if present, and integer-cent reconciliation totals.
- `journal.json`: every opening, receipt and reversal within the account export limit, with raw references, actor IDs, effective/entry dates, posting versions and idempotency identifiers. Amounts use integer cents plus decimal strings; reversals retain original-entry links.
- `journal.csv`: the same journal as a spreadsheet presentation. Formula-like or leading control-character text is prefixed with an apostrophe. JSON retains the exact raw text.
- `schedules.json`: all included saved illustrations, exact inputs/results, calculation versions and retained hashes. No recalculation or automatic selection of an illustration occurs.
- `README.txt`: scope, privacy guidance and interpretation limits.
- `manifest.json`: byte length and SHA-256 digest of each other included file, plus format version and record counts. It does not hash itself. Hashes detect accidental alteration; they are not digital signatures or proof of authorship.

Opening principal, unapplied receipts and cash control keep their existing meanings. Export does not allocate payments, accrue interest, produce an APR/payoff quote, post a correction or create legal paperwork. Current customer contacts are labeled separately from frozen draft facts. Export preparation does not freeze the underlying account against later authorized postings.

## Scope and limits

This is one account, not a complete dealership export or a restorable database/media backup. Photos, supporting uploads, demo document packets, full deal/customer histories and earlier export events are excluded. No import/restore function is claimed. Broader complete-data export remains a separate community requirement.

All journal rows are included rather than just the workspace's visible page. This version allows at most 10,000 postings, 200 illustrations and 16 MiB of uncompressed payload before the small manifest. Oversized accounts produce an explicit error instead of a misleading partial ZIP. Larger-volume export remains future work; limits must not be treated as a retention/deletion instruction.

## Security, consistency and audit

The server authorizes the book and customer against the current dealership on review and download. Readers can export their own dealership's account records; financial write permission is not granted. Responses are private/no-store and attachment downloads use an account ID rather than customer names in filenames. The ZIP is **not encrypted**; downloaded files require private storage. The production security gates remain unchanged.

The download holds the book row lock while gathering journal, context, schedules and totals. Existing receipt, reversal, linking and schedule-save services acquire the same lock, preventing interleaved application writes during capture. Linked-context and schedule hashes must verify, and the ledger must reconcile, before a ZIP is returned. Privileged database writes outside the application can bypass these conventions; no tamper-proof claim is made.

A successful GET records an immutable `DemoAccountExport` with actor, timestamp, format version, exact ZIP hash/size and posting/schedule counts in the same transaction as response preparation. An audit-write failure prevents the response. The event proves preparation of an authorized response, not delivery or receipt. Review and HEAD requests create no export event. PostgreSQL validates the audit actor's dealership role; PostgreSQL and SQLite block ordinary audit updates/deletes.

This slice exports already authorized synthetic records. It introduces no new statutory interpretation, retention deadline, legal statement or production financial rule. Refer to RAILET_PLAN.md and LEDGER_FOUNDATION.md for the applicable production gates.


Account-export verification (October 26, 2026): the full PostgreSQL suite passed 303 tests in 107.854 seconds with no skips. Nine focused export tests also passed on SQLite. Verification includes independent expected journal totals, exact ZIP/manifest hashes, linked reversals, stored schedule preservation, CSV formula safety, authorization, failed-audit rollback, HEAD behavior, database audit immutability and real PostgreSQL row-lock exclusion during capture. Browser checks downloaded a synthetic ZIP, checked all file hashes, verified visible export history and checked 1440/390/320-pixel layouts without page overflow. This is developer verification, not staff or legal validation. Private evidence: `.local/account-export-review/`.

Format **demo-account-export-v2** adds the current customer's structured contact address to account.json. Frozen linked context remains separate, and prior export events retain their original format version. No extra source data is sent to another service.

## Export format v3: demo servicing baseline

New exports use demo-account-export-v3 and preserve the selected servicing baseline in account.json (schedule ID/hash, policy version, reason, actor, creation timestamp/key). Raw immutable schedules and the full bounded journal remain in the bundle, allowing a simulation to be reconstructed with its recorded policy. Historical export audit records are unchanged. No simulation is presented as ledger allocation or a payoff.

Daily-payments extension: account export format v4 adds the immutable manual
payment_method label to journal JSON and CSV. unspecified means Not recorded;
old entries are not inferred as cash. Reversals retain their original receipt's
method. Existing export audit rows remain unchanged with their original version.

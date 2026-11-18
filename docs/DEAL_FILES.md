<!-- SPDX-License-Identifier: MPL-2.0 -->
# Private supporting deal files — development design

Supporting files (`DealFile` / `DealFileEvent`) belong to the Documents module
and reference the saved draft ID. (The Documents module also owns private
synthetic vehicle vendor invoices in `VehicleInvoice` and unverified vehicle
acquisition attachments in `VehicleAcquisitionFile`; see
[vehicle work and costs](VEHICLE_WORK_AND_COSTS.md) and
[vehicle acquisition files](VEHICLE_ACQUISITION_FILES.md).) They are not legal
forms, required-document determinations, signed-document verification, proof of
vehicle ownership, or immutable generated-deal snapshots. The original file
bytes and hash are retained while the live deal's parties and vehicle may
change. Use synthetic files only until production prerequisites are
independently satisfied.

Initial scope is PDFs only, stored privately with random server-selected names.
The application discards the original filename and does not trust its extension or
browser-declared MIME type. A bounded read, size check and PDF header/end-marker
check are only minimal format screening, not a parser, sanitizer, antivirus scan,
cryptographic signature check or proof that a document is safe to open. No inline
preview is provided. Downloads force attachment with an inert transport content
type, nosniff and a sandbox policy, after membership/dealership authorization.
Downloaded PDFs can still contain unsafe content; scanner/quarantine policy and
safe client handling remain production prerequisites.

Deal supporting-file and vehicle acquisition-file routes require
`DEAL_FILES_DEMO_ENABLED` (derived from `DEBUG`); demo packets use
`DEMO_PACKETS_ENABLED`, and vehicle vendor invoices additionally require
`RECON_DEMO_ENABLED`. These are synthetic rehearsal gates, not production
approval. Owners/staff may upload, archive and restore. Viewers see/download
active files only. Staff can also review archived files. No public storage URL,
file replacement, permanent deletion, retention timer or purge task is
introduced. Archiving retains bytes and events and does not satisfy or trigger
any statutory destruction rule. The cap counts archived as well as visible
files, so archiving is not a quota bypass. Active and archived `DealFile`,
`VehicleInvoice`, and `VehicleAcquisitionFile` records and verified PDF bytes
are also included in the owner-only synthetic documents/dealership export
(`documents/export.py`, `core/dealership_export.py`), which remains a
development export rather than a complete production backup.

## Source register and release gates

Primary sources consulted October 24, 2026. This records applicability questions
and development controls, not legal certification.

| Authority | Applicability / control | Outstanding review |
| --- | --- | --- |
| [16 CFR §314.4](https://www.ecfr.gov/current/title-16/chapter-I/subchapter-C/part-314/section-314.4) | Customer-information security requires risk-based safeguards including access controls and protection of stored/transmitted information. Per-download authorization, private storage, cache restrictions and metadata-only events support that design. | Actual deployment encryption/key management, MFA, role need-to-know, scanner/quarantine, risk assessment and service-provider controls must be verified before real data. Section-level amendment/effective-date and exception applicability review remains open. |
| [Florida §320.27, 2026 compilation](https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0300-0399/0320/Sections/0320.27.html) | Dealer recordkeeping requirements depend on the record category and operational evidence. Files are retained with their draft reference and actor/timestamps; archive is reversible and no deletion is implemented. | Confirm specific records, inspection/export needs, applicable retention periods, legal holds and effective provisions before a live filing workflow. No universal five-year deletion rule is coded. |
| Other disclosure, privacy and retention authorities in RAILET_PLAN.md | A supporting attachment is not an approved contract, credit notice, title/odometer record or e-signature workflow. | Review record-specific categorization, consent, signed artifacts, delivery and export/restore requirements before those workflows are enabled. |

The eCFR title 16 display was current through October 22, 2026; the title-wide
amendment date does not establish this section's effective dates. The Florida 2026
compilation may include provisions with differing effective dates. This slice does
not implement numeric legal deadlines or generated documents. Unresolved legal
applicability/effective dates and operational safeguards keep live behavior gated.

## Transaction and storage limits

The DB and filesystem are separate resources. Services must clean up their newly
written files on handled transaction failure, and durable upload transactions must
prevent later caller rollback after a successful storage write. Process crashes can
still leave orphaned storage objects. Reconciliation, backups including both DB and
private media, actual restore drills, storage quotas and protected infrastructure
are prerequisites before production. No claim of globally atomic disk/DB commits
or verified backup restoration follows from a passing unit test.

## Implemented behavior and verification

Luna implemented the new Documents module under explicit ownership of its new
files. The overseer integrated the registered app, private dev volume source mount,
VM sync allowlist, named routes and gated workspace navigation. Staging packaging
includes the module but staging was not deployed and its debug-derived gate is
closed. An initial migration adds only the new file and event tables with protected
references; existing financial models/services and old deal event JSON are unchanged.

Original bytes are immutable through these routes. Each upload has a per-deal UUID
submission key, SHA-256 and actual byte size. Reusing the same key/title/hash returns
the original record without rewriting bytes, adding an event or resurrecting an
archived file. Reusing a key for different content/title is rejected. File actions
and audited GET/HEAD download responses have their own events. A download event
records an authorized response/open attempt, not proof the client received every
byte or that a PDF was read. No delivery certification is implied.

Limits are 8 MiB per PDF, 100 retained files and 100 MiB per deal, including archived
files. Archive requires a reason, retains metadata/bytes and is idempotent; restore
is explicit and preserves identity/hash. No quotas are reclaimed through archive.

Independent verification on October 24, 2026:

- All 153 PostgreSQL tests passed, including simultaneous same-key uploads creating
  one record, one blob and one upload event. Existing inventory/deal concurrency,
  permissions and migration tests remain passing.
- Five additional overseer boundary cases passed locally: unauthorized GET/HEAD
  never opens storage; a database commit failure removes the new blob/rows; an
  outer transaction is rejected before writing; archive audit failure rolls back;
  file operations leave deal money/revision and financial events unchanged.
- Agent local module suite passed 23 tests with the one PostgreSQL concurrency
  case skipped there. Django checks and migration-drift check passed.
- Firefox exercised invalid-file rejection while preserving title/key, upload of a
  valid generated synthetic PDF, exact-byte attachment download, empty HEAD,
  private/no-store/nosniff/sandbox headers, archived-key retry without resurrection,
  explicit restore and 1440/390/320-pixel layouts without horizontal page overflow.

The overseer returned UI corrections before acceptance: collapsed archive options,
archived staff download links, truthful PDF reselect guidance, error focus and
unsaved-upload warning. The local model's privacy input was a narrow design review,
not source auditing or test execution. No real customer files were used. These are
developer checks, not staff usability validation, legal review or production approval.

The synthetic files and exact original bytes also survived a forced web-container
recreation using the existing private-media volume. This establishes development
persistence, not a backup restore drill. (A later disposable PostgreSQL and
private-media restore exercise in [SYNTHETIC_RESTORE_EXERCISE.md](SYNTHETIC_RESTORE_EXERCISE.md)
verified quiescent dump/restore of a synthetic PDF and database rows, which
still does not establish live production backup/recovery.) One extra synthetic
fixture from a browser harness retry was archived with a reason rather than
deleted; the demonstration Files page ends with one active and one archived PDF.

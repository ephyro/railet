# Railet: remaining work report

Snapshot: November 2026. This is a working backlog, not a delivery promise. The
local project contains more work than the last published GitHub commit; confirm
and review changes before any future publication. The current application is a
synthetic-data prototype, not ready for real dealership operations.

Developer verification on November 7, 2026: the full SQLite suite passed 608
tests with 40 skips, and the full isolated PostgreSQL suite passed 608 tests
with 2 skips. These are developer checks, not staff, legal or production
validation. On November 9, an isolated PostgreSQL suite passed 638 tests with
2 skips; a later full SQLite run covered 668 tests with 45 skips after the audit
guard migration. On November 14, the full isolated PostgreSQL suite covered
684 tests with 2 skips; the latest full runs covered 716 tests with 60 skips on
SQLite and 716 tests with 2 skips on PostgreSQL. These
developer checks do not establish production readiness.

## Where we are

The prototype has shared customers and inventory, a deal desk, draft Florida tax
estimates, synthetic deal-completion snapshots (and an internal void rehearsal
when no BHPH account is linked), private PDF attachments (deal files, vendor
invoices, and unverified vehicle acquisition attachments), reconditioning tasks
and itemized costs, manual customer activity/follow-ups and an offline mock
message simulator, an inventory investment and aging report, owner-only
synthetic exports, and a disposable PostgreSQL/media restore exercise. BHPH
includes a synthetic ledger, opening balances, unapplied receipts and reversals,
and an installment-coverage simulation. A completed BHPH rehearsal can open or
link a synthetic account using frozen deal facts.

These features establish useful workflows, but test receipts do not reduce
contractual principal, simulated due status is not a legal delinquency decision,
a completed or voided rehearsal is not a finalized sale, contract, or legal
cancellation, and owner exports/restore exercises are not complete production
backups. Developer tests are not a substitute for testing by dealership staff or
professional review.

## Priority 1: make the core workflow usable for a controlled pilot

### Deal and inventory lifecycle

- [ ] Define real deal states, sale/reservation/cancellation, vehicle ownership and
  sold-stock transitions; handle duplicate VINs, reacquisitions and trade intake.
  A read-only synthetic duplicate VIN report lists matching same-dealership stock,
  including sold records, with 25 vehicle rows per page. Ordinary entry, trade
  intake and this report share database upper/trim matching, including tabs and
  other surrounding whitespace; blank VINs are excluded. Database case behavior
  is not a universal VIN canonicalizer, especially for non-ASCII legacy data. A match
  does not resolve duplicates or verify reacquisition; reconciliation stays open.
- [ ] Design and implement controlled corrections, voids and amendments with
  preserved deal/document/financial history. The rehearsal is currently frozen
  with no reopen or amendment path. An internal, immutable synthetic void
  rehearsal now blocks future BHPH handoff when no account is linked; it is
  not legal cancellation and does not correct a sale, payment or balance.
  A separately reviewed synthetic follow-on draft can preserve source provenance
  without changing the original. Account-linked corrections, live amendments and
  real cancellation remain unresolved.
- [x] Add optional recorded acquisition dates and inventory aging filters; old
  records remain unknown. Staff-entered dates are not independently verified.
- [ ] Capture sale dates and verified acquisition evidence for reliable time-to-sale
  reporting and ownership history.
  (Implemented optional staff-entered `sold_on` dates for vehicles marked `Sold`
  with chronology validation, audit/revision history, and synthetic time-to-sale
  display/filtering on the inventory investment report and CSV export. Private
  synthetic acquisition PDFs can be retained and exported as unverified
  staff-provided evidence; verified ownership evidence and finalized deal-driven
  sale transitions remain open. See [acquisition files](VEHICLE_ACQUISITION_FILES.md).)
- [ ] Expand the 2026-only Florida draft tax profile to reviewed effective-date
  tables and transaction cases; validate exemptions, trade and fee treatment and
  out-of-state cases with a Florida tax professional. Current estimates are not
  filing or legal determinations.
- [ ] Test the entire workflow with dealership staff using invented records; record
  observations and resolve confusing navigation and unnecessary steps.

### Documents and signing

- [x] Add a private, synthetic paperwork-topic review, title-preparation worksheet and deal-terms practice view
  based on a saved demo snapshot, with integrity checks and links to official sources.
  These screens are not legal forms, do not determine applicability or readiness,
  and do not create signed or finalized documents. See [Florida document research](FLORIDA_DOCUMENT_RESEARCH.md).
- [x] Preserve the selected research references and inventory version in new demo packet HTML; require a fresh preview when the inventory version changes.
- [x] Create an initial versioned research inventory for synthetic cash and BHPH reviews; it records unknown rights and revision information and does not determine legal applicability.
- [x] Expand the synthetic FTC Buyers Guide research with official rule and dealer guidance, source dates, limited reuse guidance, display, delivery and Spanish-language research; legal interpretation and production form rights remain open. See [Florida document research](FLORIDA_DOCUMENT_RESEARCH.md).
- [x] Record selected closed-end disclosure categories and Florida itemization and
  timing research in catalog v6; transaction applicability, effective dates,
  financial calculations, forms and counsel review remain open. No live credit
  disclosures are enabled. See [Florida document research](FLORIDA_DOCUMENT_RESEARCH.md).
- [ ] Verify the current HSMV 82040 MV PDF, applicable procedures and reuse/filing acceptance directly with FLHSMV; the 2026-11-07 research was limited to indexed official text because direct PDF access returned 403. No title-form generation or filing is enabled.
- [ ] Inventory each distinct needed document for ordinary Florida cash and BHPH
  transactions and special cases; record owner, form source, current revision,
  permitted use, applicability, required facts, delivery and retention. Get counsel
  to approve the list and wording; do not copy proprietary vendor forms.
- [ ] Build a versioned form registry, authoring and approval lifecycle, explicit
  applicability rules, missing-field controls, rendering and immutable artifact
  storage only after document-specific requirements and permissions are verified.
- [ ] Test rebuilt, unknown-brand, co-buyer, trade-in and cash/BHPH combinations
  against independently reviewed cases, including changes after finalization.

- [ ] Obtain rights to current Florida forms; review applicability, versions,
  document-specific required facts, rebuilt-title disclosures, odometer rules,
  delivery and retention with qualified reviewers.
  (Research registry v5 records federal odometer and Florida reassignment/secure
  power-of-attorney sources, exceptions and open acceptance/rights questions;
  no applicability decision or live form is enabled. See
  [Florida document research](FLORIDA_DOCUMENT_RESEARCH.md).)
- [ ] Build approved document packs, applicability checks, previews, immutable
  generated versions and signed-artifact retention/export.
- [ ] Connect DocuSeal in an isolated test environment using a synthetic template
  and PDF. An in-memory mock exercises an invented test contract; no provider
  connection, signing UI, verified webhook, signed-document retrieval or
  provider end-to-end test exists. See [DocuSeal rehearsal](DOCUSEAL_REHEARSAL.md).
  A parseable, visibly marked synthetic PDF fixture and stricter offline request
  allowlist are prepared; the November 9 local check could not access Docker's
  socket, so actual provider version and egress/notification controls remain open.
- [ ] Verify provider version, notification suppression, authentication, webhook
  authenticity/replay handling, retries, artifact integrity and duplicate request
  handling. Review DocuSeal AGPL and attribution obligations for the chosen setup.
- [ ] Review E-SIGN/UETA consent, record delivery and document eligibility; title
  and odometer forms may have separate acceptance rules. Enable no live signing
  until these requirements and security/provider prerequisites are approved.

### BHPH and financial integrity

- [ ] Implement independently verified contract schedules and disclosures, including
  applicable APR/finance charge calculations, odd first periods, supported payment
  frequencies and precomputed vs. simple-interest methods.
- [ ] Design and review actual payment allocation, contractual interest/accrual,
  fees, partial/early/late payments, reversals, deferrals, extensions, refunds and
  payoffs. Keep posted amounts, effective dates and calculation versions auditable.
- [ ] Implement statements, reviewed amount-due and delinquency calculations,
  collections/dispute holds, repossession/bankruptcy controls and reconciliation.
  These depend on reviewed contracts and rules; do not turn demo coverage into a
  live balance merely by removing a gate.
- [ ] Build migration/import and reconciliation against authorized source exports,
  preserve exceptions, and specify one authoritative ledger at cutover.
  (An explicitly gated offline [synthetic account comparison rehearsal](SYNTHETIC_MIGRATION_RECONCILIATION.md)
  compares invented integer-cent summaries, preserves unknown amounts, and reports
  missing, duplicate, unresolved and differing entries. It does not import, persist, post or
  establish source authority; actual migration and reconciliation remain open.)
- [ ] Complete real payment-provider onboarding, settlement/returns, idempotency,
  reconciliation, authorization and PCI/provider review before live payments.
- [x] Support linking an existing unlinked synthetic account to a completed
  rehearsal using a verified frozen snapshot and an explicit preview. Focused
  SQLite checks passed; PostgreSQL checks included concurrent link attempts.

### Security, operations and data ownership

- [ ] Implement and test MFA, production security configuration, encryption and
  key management, least-privilege roles, session controls, monitoring and an
  incident-response process appropriate to actual deployment and data flows.
  [MFA design](MFA_DESIGN.md) records preliminary FTC/NIST research, candidate
  dependencies and a staged enrollment, recovery and enforcement plan. Library,
  key custody, rollout and legal/security review remain open; no MFA is enabled.
  An isolated synthetic TOTP factor/replay/throttle experiment exists without login
  integration or real identities; it is not production MFA. See [MFA design](MFA_DESIGN.md).
  A development-only, explicitly keyed synthetic AES-GCM helper now covers
  isolated secret encryption and key-rotation rehearsal; it stores nothing and
  is not connected to authentication. Production key management remains open.
- [ ] Independently verify dealership isolation and authorization, private file
  access, audit integrity, dependency/secret handling and provider integrations.
  Synthetic ledger posting authorization review: opening, receipt and reversal
  previously checked membership without locking it and did not check active user
  status, allowing a change before commit. Posting transactions now lock the
  dealership, then the book for receipt/reversal, and recheck/lock active
  owner/staff membership and user before retry handling or insertion. The confirm
  view takes the dealership lock before its existing book lock; draft opening
  already takes the dealership lock before calling `open_book`. Existing posting
  pairs, idempotency keys and append-only history are unchanged. PostgreSQL-only
  tests cover role revocation during each posting and inactive/foreign membership.
  Twenty ledger and concurrency tests passed against a uniquely named disposable
  PostgreSQL database. The focused SQLite ledger/view/account suite ran 37 tests
  with five PostgreSQL-only skips, including inactive-actor rejection for all
  three posting types and balanced history.
  Concurrent active-status and dealership transfers, cross-module lock ordering,
  and PostgreSQL lock/deadlock behavior remain unverified. Other finance services
  using `require_member` are outside this posting-specific authorization change.
  Account setup/link follow-up: `open_from_draft`, `link_draft` and
  `link_completed` formerly checked membership before their dealership lock,
  including before existing-context retry returns, without checking active user
  status. They now recheck and lock the active owner/staff membership and user
  after locking the dealership, before reads, retries or writes. Existing deal,
  book, snapshot and posting paths remain intact; dealership-first serialization
  is shared with synthetic posting. PostgreSQL-only tests cover role revocation
  while opening or draft linking waits and user deactivation while completed
  linking waits. SQLite ran 24 account/handoff tests with six PostgreSQL-only
  skips, including inactive-actor denial before and after an existing link.
  Twenty account and concurrency tests passed against a uniquely named disposable
  PostgreSQL database. Dealership-transfer races and cross-module deadlock behavior
  remain unverified. No existing database was changed.
  Schedule/baseline authorization follow-up: `save_illustration` and
  `select_baseline` previously checked membership before acquiring the book lock
  and did not check active status. They now lock dealership then book, and recheck
  and lock the active owner/staff membership and user before retry handling or
  saving. Their reviewed HTTP callers do not hold a prior book lock when invoking
  these saves. Idempotency and immutable snapshot checks remain in place; no
  ledger posting is created by either operation. A PostgreSQL-only test covers
  role, dealership and active-status changes while each save waits. Twenty-eight
  focused PostgreSQL tests passed in a uniquely named disposable database. The
  focused SQLite suite ran 28 tests with three PostgreSQL-only skips, including
  rejection of inactive actors on a baseline retry and schedule save. Other
  cross-module lock ordering and deadlock behavior remain unverified; no existing
  database was changed.
  Finance lock-order source audit: reviewed schedule `save_illustration`,
  servicing `select_baseline`, account linking/opening, ledger posting and
  confirm/prepare callers, account ZIP download, finance module export and
  dealership ZIP orchestration. Schedule, baseline, linking and posting writes
  acquire the dealership row before book and membership/user locks, serializing
  those reviewed paths within a dealership despite differing inner lock orders.
  Account ZIP download locks its book and writes its export event, but does not
  explicitly request dealership or membership locks afterward. Finance module
  export locks owner membership and reads without explicit book/dealership locks;
  the dealership ZIP takes dealership first before invoking it. No concrete
  inversion among these paths was established, so lock behavior was not changed.
  The focused SQLite schedule, servicing, account and export suite ran 60 tests
  with four PostgreSQL-only skips. A Unix-socket bind probe returned `Operation
  not permitted`; PostgreSQL lock waits, foreign-key interactions, administrative
  transactions and cross-module callers remain unverified by this audit. Existing
  databases were not changed; tests used synthetic records.
  November 14 synthetic customer-activity review inspected `customers/activity.py`
  and its forms: activity mutations are implemented in views, with no separate
  activity mutation service to call. Focused SQLite tests cover anonymous access,
  local viewer/staff/owner and foreign owner direct URLs, create/edit/complete,
  cross-customer activity IDs, assignment choices, stale revisions, queue/history
  isolation and an archived linked draft. The customer/activity models have no
  archive state; archiving a linked draft does not archive its customer activity.
  Fifteen `customers.test_activity` tests passed on SQLite, including existing
  retry, CSRF and audit rollback checks. PostgreSQL concurrency, role changes
  during requests, direct database access and other modules
  were not verified by this review; no broad security certification is implied.
  A separate November 14 deal-follow-up review exercised anonymous, viewer,
  staff, owner and foreign-owner URL access, foreign deal/task IDs and mutation
  attempts, archived drafts, stale edits and invalid assignments. The internal
  save helper now rejects a task belonging to another deal, rechecks active
  editor membership, and validates assignees before retry/no-op returns. Direct
  helper tests cover mismatched parents and tampered cleaned assignments. Fourteen
  `deals.test_followups` tests passed on SQLite, including existing CSRF, retry
  and audit rollback checks. PostgreSQL was stopped and no server was started;
  concurrent membership/assignment changes and parent/task lock behavior were
  not tested here. The helper still requires its caller to lock the scoped parent;
  this review does not establish a broad security certification.
  Follow-up PostgreSQL concurrency tests were added for simultaneous same-key
  creation retries (one task and one event) and competing same-revision edits
  (one save, one conflict, one matching event). Both tests passed against a
  uniquely named disposable database on the local PostgreSQL integration server.
  The combined SQLite run passed 14 existing follow-up tests and skipped those
  two PostgreSQL-only checks. The worker's separate temporary cluster could not
  bind its socket; its files remain under `/tmp/railet-followup-pg-3KMa53CL`.
  Role/assignment races and lifecycle concurrency are outside these two tests.
  A subsequent November 14 review found membership and active-user checks could
  change before a follow-up write committed. POST now locks the dealership,
  then deal/task, followed by actor/assignee membership rows and user rows in
  stable ID order; authorization is rechecked under those locks. The caller of
  `save_form` must hold dealership and deal locks in a transaction. Added two
  PostgreSQL-only checks for in-flight role/deactivation changes and revocation
  before authorization. All 18 follow-up tests, including the four concurrency
  cases, passed against a uniquely named disposable PostgreSQL database. SQLite
  passed 14 existing tests and skipped the four PostgreSQL-only tests. Other
  administrative lock orders and deadlock behavior remain unverified; no existing
  database was changed.
  A lock-order audit identified a potential dealership/membership wait cycle
  between follow-up saves and foundation export; it was not reproduced as an
  actual deadlock. The subsequent fix makes foundation export lock the dealership first,
  then rechecks and locks the active owner membership and joined user. The
  dealership ZIP uses that authorization within its existing atomic transaction
  before capture and audit. Missing dealerships are denied. PostgreSQL-only tests
  now exercise overlapping foundation export/follow-up saves and owner demotion
  while export waits for the dealership lock. After correcting a disabled test
  gate, 25 focused PostgreSQL tests passed in a uniquely named disposable
  database. The combined SQLite suite ran 39 tests with six PostgreSQL-only skips.
  Other administrative/module lock orders and production consistency remain open.
  A subsequent export lock-order review covered customer review/download and
  component, inventory authorization/component, documents and finance module
  exports, dealership ZIP orchestration, and customer activity, inventory
  mutations, document upload/packet and finance account/posting locks. Standalone
  inventory export previously locked membership before dealership; customer
  download locked membership before inserting an audit event with a dealership
  foreign key, which can wait for a dealership row lock. Both authorization
  paths now lock dealership before rechecking the active owner; audit creation
  remains in the existing transaction. Document and finance module exports hold
  owner membership but do not explicitly lock the dealership or write their own
  audit event; no corresponding inversion was established in the reviewed paths.
  A PostgreSQL-only test checks that customer and inventory authorization wait
  on dealership before acquiring membership; 15 focused PostgreSQL tests passed
  in a disposable database. The focused SQLite suite ran 22 tests with one skip.
  PostgreSQL FK-lock behavior, race/deadlock freedom, external/admin paths and
  consistent filesystem snapshots remain unverified by this review.
  Feedback-export follow-up: its standalone authorization now locks dealership
  before rechecking and locking the active owner membership; missing dealerships
  are denied. The dealership ZIP still captures feedback inside its existing
  transaction and records package preparation, not confirmed delivery. The
  feedback component remains unredacted and dealership-scoped. A PostgreSQL-only
  lock-order regression waits for a blocked exporter and verifies its membership
  row is still available. The feedback, dealership-export and follow-up PostgreSQL
  suite passed 25 tests in a disposable database. The feedback and dealership-export
  SQLite suite ran 19 tests with one PostgreSQL-only skip. Other concurrent
  role changes, cross-module lock orders and production recovery remain open.
  Synthetic BHPH account and export access received focused SQLite and PostgreSQL
  checks. A SQLite migration restores export audit guards lost during table
  rebuilds; existing databases must apply it. A focused dealership ZIP review
  checked owner reauthorization, scoped components, audit failure and private
  artifacts. It fixed normalized private-path aliases that could otherwise cross
  dealerships if stored file references were inconsistent. A further focused
  review covers direct synthetic deal, acquisition and invoice PDF downloads and
  vehicle photo/thumbnail URLs: dealership and role checks, archived-file
  visibility, anonymous access, no-store responses, missing/corrupt files and
  failed download audits. A later service-boundary review found that deal-file
  upload/archive trusted the supplied actor and invoice upload did not recheck
  active status. These synthetic mutations now lock dealership then parent and
  recheck a locked active editor before retries or writes; acquisition mutations
  use the same order. Focused SQLite checks ran 47 tests (two skips), PostgreSQL
  ran 47 tests, and a separate PostgreSQL regression verified role/deactivation
  changes while five mutation types waited on the dealership lock, and verified
  role/deactivation writes wait for deal, invoice and acquisition uploads to
  commit once authorization is locked. Existing
  private bytes and event history are preserved; wider administrative lock
  ordering and unrelated services remain open. Malformed or cross-dealership storage aliases are
  rejected, and deal PDFs are checked against retained size and hash. Invoices
  and saved packets do not have an archive state. Photo downloads have no stored
  content hashes or download audit. Marked document and photo wrappers now pass
  unexpected exceptions to Django normally, while an outer middleware adds
  private no-store headers to the resulting 500 responses. This covers errors
  after a wrapper is entered; failures earlier in middleware or URL resolution
  are not marked, and errors after streaming starts cannot change sent headers.
  File reads and reference checks are not a coordinated snapshot, and privileged
  filesystem/DB changes, reference-scan scaling and a broader independent
  security review remain open.
- [ ] Provide complete dealership data export and tested database **and private
  file** backup/restore, including recovery drills and migration/upgrade plans.
  Owner-only synthetic customer JSON exports now cover customer records, activity
  and change history with an audited download; concurrent changes can affect
  consistency. Internal, owner-gated export components also cover foundation,
  customer, deal, inventory, document, finance, and feedback records; inventory
  photos and document artifacts are included in their respective components.
  An owner-only synthetic ZIP now combines these components and audits its
  preparation. Foundation export v2 includes bounded prior dealership ZIP
  preparation events, including their actor, time, format, size and hash; each
  package's own event is recorded after that package is built and appears only
  in a later export. Customer export v3 also includes bounded prior same-dealer
  customer export-preparation events; the event for a customer download is
  recorded after its bytes are prepared and is included only in later exports.
  The package excludes credentials and personal saved views, does not guarantee
  a coordinated database/file snapshot, and has no import or restore.
  On November 10, 2026, the disposable synthetic restore exercise passed on
  PostgreSQL 17.11 with current migrations: two restored inventory audit rows
  matched their captured baseline; valid insert, mismatched insert rejection,
  update/delete rejection and audited-vehicle ownership protection were checked
  alongside restored deal PDF, vehicle invoice, acquisition PDF, photo and
  thumbnail bytes and scoped downloads. The expanded drill also restored an
  invented ledger book, opening, receipt and linked reversal with exact captured
  fields, expected balanced totals, and book/posting update/delete guards.
  Five exercise safety tests passed. This
  quiescent synthetic run did not verify historical mismatches,
  concurrent races, all financial record or artifact types, or a live recovery. These exports and
  the exercise do not prove complete dealership export or production recovery.
  See [customer export](CUSTOMER_EXPORT.md) and
  [synthetic restore exercise](SYNTHETIC_RESTORE_EXERCISE.md).

  On November 13, 2026, the isolated PostgreSQL 17.11 drill also verified a
  restored synthetic demo packet's captured fields, hashes, versions, scoped
  download and unchanged artifact after a rolled-back source-customer edit;
  five safety tests passed. This does not verify every packet version or live recovery.

  **Current model and artifact inventory:** The module exports cover dealership
  and membership provenance and prior dealership exports; customers, activities,
  change and export events, and mock-message histories; vehicles, photos, vendors,
  reconditioning tasks, costs and vehicle audit events; drafts, proposals, trades,
  follow-ups, completion/void/follow-on records and their histories; documents,
  packets, invoices and acquisition-file records and events; finance books,
  postings, schedules, contexts, servicing plans and account-export events; and
  feedback reports. Referenced private vehicle originals/thumbnails and the three
  PDF attachment categories are included, including archived records; frozen
  packet HTML is included from the database. These are scoped records, subject to
  component bounds and integrity checks, not a claim that all stored data is
  recoverable. Inventory export checks audit records involving either the
  requested dealership or one of its vehicles in a single query; an inconsistent
  dealership/vehicle link aborts either affected dealership's export without
  exposing the record. Migration `core.0008_inventory_audit_guards` installs
  SQLite/PostgreSQL triggers rejecting new mismatched audit inserts and audit
  updates/deletes, and prevents changing a vehicle's dealership once audit history
  exists. PostgreSQL locks the vehicle row during audit insertion to serialize
  it with ownership changes. Apply the migration to existing installations;
  reversing it removes these protections. Existing inconsistent rows are retained
  unchanged and still block either affected export pending a separately reviewed
  resolution. PostgreSQL `TRUNCATE` is not covered by row-level DELETE triggers,
  and database privileges or trigger controls can bypass these protections;
  deployment roles and maintenance procedures still need review. Future SQLite
  migrations rebuilding either guarded table must preserve and verify the
  triggers. Concurrent
  exports remain subject to the snapshot limitations above.

  No additional safely scoped ordinary dealership-owned model category was found
  in this code inventory. Personal saved views, credentials, sessions and secrets
  are intentionally excluded. The synthetic MFA prototype's factors contain
  encrypted secrets and use free-form synthetic references rather than dealership
  foreign keys; its events cannot safely be attributed to a real dealership from
  those references. Orphaned storage objects and prior generated export ZIP bytes
  are not included; export-event hashes do not recreate those bytes. Photo hashes
  are calculated at export, not retained from upload. This is a source inventory,
  not a coordinated snapshot, complete backup or production-readiness assessment.
- [x] Document a record-specific retention and legal-hold design without enabling
  deletion (November 13, 2026). [Research and proposed controls](FLORIDA_RETENTION_RESEARCH.md)
  map current models, snapshots, private files and exports to known versus missing
  trigger evidence; define provisional/confirmed holds, scope, independent release
  approval, actor/audit requirements, export/backup custody and exception handling.
  A targeted primary-source recheck records currency and access limits; the
  November 7 DOR/form research is not represented as freshly verified.
- [ ] Review and implement retention classifications and legal holds separately
  from disposal. Resolve transaction-specific dates, current OFR rules, blocked
  Safeguards rule text, inaccessible 12A-1.012 final text and DOR discrepancies
  with legal/CPA reviewers; designate custodians and privacy-review owners.
  Verify permissions, overlapping/future scopes, independent releases, concurrent
  changes, immutable evidence, export completeness and newer-hold replay after
  older database/private-file restores using synthetic fixtures. No hold runtime
  checks or legal/staff approval are claimed by the documentation task.
  Automatic deletion remains disabled; no universal period, disposal action or
  backup-expiration workflow is authorized. Existing deletion/cleanup paths still
  require inspection before they can be described as hold-aware.
  An explicitly gated, offline `core/hold_rehearsal.py` exercises overlapping
  synthetic holds, unknown scope, independent release and reactivation with
  immutable in-memory events. Five isolated tests passed; it has no database,
  deletion or operational authorization and a clear hold check is not permission
  to dispose. History and immutable-container validation now reject a manually
  constructed released hold with no event history and inconsistent transitions.
  Validation checks structure only: a fabricated but consistent event history
  is not authenticated, authorized or proof of an actual hold decision.
  Persistent holds, professional review and enforcement remain open.
- [ ] Complete the applicable federal and Florida compliance register with current
  authorities, effective dates, exceptions, controls, owners, evidence and legal
  and financial review. The project plan is a starting point, not a certification.

## Priority 2: practical day-to-day modules

### CRM and SignalWire

- [x] Add an offline, synthetic-only message event simulator with fixed mock labels and retain its history in customer exports. This is partial progress; it does not connect to SignalWire or establish delivery or consent.

- [x] Extend the current manual customer notes, follow-ups, appointments and queue
  with lead stages, richer search, activity history and useful handoffs to deals.
  (Implemented optional sales lead stages, contact/assignee/activity search,
  activity history filters, and direct links to existing deals or starting a deal
  on synthetic customer profiles; lead stages are internal sales labels only and
  do not represent communication consent, credit decisions, or completed sales.)
- [ ] Design optional SignalWire calling/texting around explicit purpose and
  consent, opt-out/suppression, approved hours, delivery history, costs and access
  controls. Research current applicable federal/Florida requirements and provider
  behavior before enabling live calls, texts or automated collections.
  (Researched primary federal TCPA/FCC `47 C.F.R. § 64.1200`, Florida FTSA
  `§ 501.059`, Florida Telemarketing Act `§§ 501.604` / `501.616(6)`, Florida
  FCCPA `§ 559.72`, and official SignalWire webhook/callback reliability docs
  in [SignalWire research](SIGNALWIRE_RESEARCH.md); effective-date/amendment
  verification, Florida counsel review of exemptions/exceptions, provider
  sandbox verification, and live calling/texting remain open and disabled.)
- [ ] Add sandbox provider adapters, delivery events and idempotent retries; make
  sure delayed or duplicated callbacks cannot misstate delivery or consent.

### Reconditioning and vendors

- [x] Expand vendor records with appropriate contacts and permissions; support
  private invoice attachments linked to vehicles and itemized costs.
  (Implemented vendor contact details—contact person, phone, email, address,
  notes—with dealership isolation, owner/staff editing, revision checks, and
  change history in `inventory`; private synthetic vehicle invoice PDF
  attachments linked to vehicles and itemized costs were independently verified
  with 39 SQLite tests passing and 1 backend-specific skip.)
- [x] Add task editing, assignment, scheduling and useful aging/queue filters;
  distinguish an operational work status from a safety inspection or sale approval.
  (Implemented for synthetic reconditioning tasks and the work queue; operational
  task statuses do not verify safety inspections or approve a vehicle for sale.
  The queue summarizes open, in-progress, done, overdue open and unscheduled
  open work across the current filtered results, including all pages. On
  2026-11-10, a developer used headless Firefox 158 with a temporary synthetic
  SQLite database and loopback server to check a 1440px desktop and 390px
  mobile view, 320px overflow, search, scope and page-two counts, visible focus
  and keyboard activation of Completed, accessible names for search and summary,
  and exclusion of a foreign dealership's task and counts. A duplicate mobile
  status badge was removed; 32 focused SQLite tests passed. This was not a
  dealership staff test, a full accessibility audit, or a production check.)
- [ ] Reconcile purchase costs, fees and reconditioning with accounting once a
  reviewed accounting integration exists. Current internal cost entries do not
  create vendor payables or payment records.
  (Specified versioned GL account mappings, illustrative balanced journal
  entries, provenance, reversal handling, reconciliation exception classes, and
  cutover ownership in [accounting mapping design](ACCOUNTING_MAPPING_DESIGN.md);
  CPA review and live accounting/AP integration remain open.)

### Reports and accounting

- [ ] Extend inventory aging with verified dates and time-to-sale; add reviewed
  sales, reconditioning, BHPH activity and reconciliation reports.
  (Synthetic time-to-sale reporting and filtering from chronological
  staff-entered `acquired_on` and `sold_on` dates are now included on the
  inventory investment report; verified ownership/sale evidence and reviewed
  sales, reconditioning, and BHPH reconciliation reports remain open.)
- [ ] Define date, status, correction and permission semantics for each report;
  support safe filtered exports without exposing other dealerships' data.
  (Implemented dealership-scoped, formula-safe CSV exports on the synthetic
  inventory investment report, the reconditioning work queue, each vehicle's
  itemized cost register, and BHPH payment activity with explicit recorded-cost,
  reversal, operational, and unapplied-payment semantics. Reviewed sales and
  reconciliation report exports remain open.)
- [ ] Design accounting mappings, general-ledger integration, reconciliation and
  optional QuickBooks integration. Current recorded-cost differences are not net
  profit and the synthetic finance journal is not full dealership accounting.
  (Documented the configurable mapping, provenance, reversal, and reconciliation
  architecture in [accounting mapping design](ACCOUNTING_MAPPING_DESIGN.md);
  dealer/CPA chart-of-accounts review, GL export implementation, and optional
  QuickBooks integration remain open.)

### Other modules considered

- [ ] Decide scope and value for a transporter marketplace. Research broker/carrier
  roles and obligations, insurance evidence, disputes and payments before live use.
- [ ] Evaluate licensed valuation data, credit bureaus, websites/marketing and
  integrations only after their provider agreements, privacy and cost are clear.

## Priority 3: launch and community

- [x] Produce a safe, accessible demonstration of vehicle → customer → deal →
  synthetic completion → BHPH account → test payment; use invented information.
  (Documented step-by-step in [BHPH demo walkthrough](BHPH_DEMO_WALKTHROUGH.md)
  and verified by developer browser/test checks; dealership-staff usability
  sessions remain open in Priority 1. The [staff workflow protocol](STAFF_WORKFLOW_TEST.md)
  now prepares uncoached vehicle-to-reversal tasks and private observation notes;
  preparation is not evidence that a staff session occurred.)
- [ ] Add current screenshots or a short walkthrough and clear contributor tasks;
  recruit a few dealership reviewers and record their findings without real data.
  (Linked the [synthetic BHPH walkthrough](BHPH_DEMO_WALKTHROUGH.md) and added
  concrete contributor starting points, verification expectations, and
  production-gate boundaries in `CONTRIBUTING.md`; current screenshots and
  dealership reviewer recruitment/sessions remain open.)
- [ ] Review README and other historical documents for stale status claims; keep
  public feature descriptions and production limitations accurate.
  (`README.md`, `CONTRIBUTING.md`, `docs/DEVELOPMENT.md`,
  `docs/BHPH_DEMO_WALKTHROUGH.md`, `docs/STAFF_WORKFLOW_TEST.md`,
  `docs/DEAL_FILES.md`, `docs/DEMO_PACKETS.md`, `docs/DOCUSEAL_REHEARSAL.md`,
  `docs/VEHICLE_WORK_AND_COSTS.md`, `docs/VEHICLE_ACQUISITION_FILES.md`,
  `docs/DEAL_REVIEW.md`, `docs/DEMO_COMPLETION.md`,
  `docs/BHPH_ACCOUNT_WORKSPACE.md`, `docs/LEDGER_FOUNDATION.md`,
  `docs/ACCOUNT_EXPORT.md`, and `docs/PAYMENT_REGISTER.md` updated to reflect
  current synthetic modules, unverified acquisition/invoice attachments,
  demo-summary-v6 research packets, mock-only DocuSeal boundaries, completion
  void rehearsal, completed-rehearsal account handoffs/linking,
  unapplied-payment and demo-servicing boundaries, payment-register CSV export,
  SQLite audit-guard restorations, limited owner exports, disposable restore
  exercise, and unvalidated staff-testing status; review of remaining older
  per-slice historical docs in `docs/` stays open before any public release.)
  On November 9, source and template review also covered exactly
  `docs/ACCOUNT_SEARCH.md`, `docs/CUSTOMER_ADDRESSES.md`,
  `docs/CUSTOMERS_AND_DEALS.md`, `docs/DEAL_FOLLOWUPS.md`,
  `docs/DEAL_HISTORY.md`, `docs/DEAL_TYPES_AND_TERMS.md`,
  `docs/DRAFT_ARCHIVING.md`, `docs/PHOTOS_AND_FILTERS.md`, and
  `docs/TRADE_INS.md`. Corrected current synthetic capabilities and labeled dated
  verification; this does not complete review of other historical documents or
  establish staff validation, legal approval or production readiness.
  A further November 9 source/template review covered exactly
  `docs/DEMO_PACKET_EXPORT.md`, `docs/DUPLICATE_VIN_REVIEW.md`,
  `docs/FEEDBACK.md`, `docs/FLORIDA_DRAFT_TAX.md`, `docs/IMPLEMENTATION.md`,
  `docs/PRINTABLE_RECEIPTS.md`, `docs/SCHEDULE_METHODS.md`,
  `docs/UI_SIMPLIFICATION.md`, and `docs/UX_PRINCIPLES.md`. Dated design,
  developer evidence and legal research remain historical; other unlisted older
  documents and future changes still need review before public release.
  On November 13, a source-only operational review covered exactly
  `docs/DEVELOPMENT_VM.md`, `docs/POSTGRES_INTEGRATION.md`,
  `docs/STAGING_VM.md`, `docs/IMPLEMENTATION.md`, `docs/FEEDBACK.md` and this
  backlog. Compared `dev/vm/{start,sync}.sh`, `dev/postgres.sh`, both Compose
  files, staging Dockerfile/Caddyfile/secret initializer, base/staging settings,
  seed command, feedback views/forms/models/export/routes/account-menu template,
  inventory audit migration and disposable restore script. Corrected historical
  environment/current-migration claims, sync overwrite/filter limits, PostgreSQL
  prerequisites/inherited environment limits, password-file seeding, debug-off
  staging feature gates, loopback tunneling, backup scope/no-clobber handling,
  inventory audit guards and feedback retention/error-cache/export boundaries.
  Local links, whitespace, shell syntax and Python parsing were checked; no
  deployment, VM boot/sync, database operation, reset, Git operation or runtime
  feature/security test was performed. Existing-VM upgrades, staging image/build,
  TLS/proxy/login/static behavior, unexpected feedback-error cache handling,
  coordinated backup/key recovery and a current full-suite run remain unverified
  by this review. Historical results were retained as historical evidence; other
  unlisted documents, dependency/version security and legal approval were not
  reassessed. Synthetic-only and production release gates remain unchanged.
- [ ] Review current files **and Git history** for private DealerCenter captures,
  customer data, credentials, proprietary marketing-site files and license notices
  before any future push. Publish only when explicitly authorized.
  November 13 [current-tree exclusion review](PUBLIC_RELEASE_REVIEW.md) inspected
  filenames/metadata for private material and source/configuration notices without
  opening captures, environment files or databases. Fixed Git/Docker exclusion
  gaps for saved report captures, legacy assets, hosting state, credentials,
  database sidecars, dumps/backups and exports; qualified the third-party notice's
  distribution claim. Targeted static checks do not establish clean artifacts.
  The November 14 follow-up added the project's declared MPL identifier to exactly
  the seven generated migrations listed in the review, preserving their original
  bytes and generated headers; AST comparisons confirmed no behavior changes.
  Missing identifiers are resolved, but contributor attribution, provenance and
  historical licensing exceptions remain unverified without history. Legacy
  asset provenance, arbitrary data filenames, synthetic-content verification,
  exact release artifact/dependency review and actual tracked/history review
  remain open. `.git` is empty; history is unavailable and was not initialized.
  No Git operations, deletion, build, commit or publication occurred.
- [ ] Keep the core safe and useful under MPL 2.0. Validate paid support, migration,
  hosting and enterprise demand and costs before promising pricing or features.

## Suggested next sequence

1. Observe the synthetic end-to-end flow with staff and fix the largest usability gaps.
2. Verify acquisition dates, add sale-date tracking, and expand basic reports.
3. Build a local DocuSeal test integration with a synthetic document and verify the
   full signed-artifact lifecycle without sending real communications.
4. Work with a Florida dealer attorney, tax professional and finance specialist on
   the specific deal/documents/BHPH cases the first pilot must support.
5. Implement the reviewed financial and document workflows, then security,
   export/restore and migration checks; run a controlled pilot only after its gates
   and explicit owner authorization are satisfied.

Related details: [product and compliance plan](RAILET_PLAN.md),
[DocuSeal research](DOCUSEAL_REHEARSAL.md), [completion rehearsal](DEMO_COMPLETION.md),
[demo servicing](DEMO_SERVICING.md), [ledger foundation](LEDGER_FOUNDATION.md),
[vehicle work and costs](VEHICLE_WORK_AND_COSTS.md), and
[staff workflow session](STAFF_WORKFLOW_TEST.md).

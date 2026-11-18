# Disposable synthetic database and private-file restore

Run from the project root as an unprivileged user:

```sh
.venv/bin/python dev/restore_exercise.py
# Optional: --pg-bin /path/to/compatible/postgresql/bin
```

Requires the project's Python environment and `initdb`, `pg_ctl`, `createdb`, `pg_dump`, and `pg_restore`. The default tool path is `.local/pg-integration/install/bin`. It creates a fresh, owner-only temporary workspace under `/tmp`, initializes a separate cluster with no TCP listener and a private Unix socket, creates fresh source and destination databases, migrates the source, and inserts only invented records. It uses the application services to store a synthetic deal PDF, vehicle invoice, acquisition PDF, and vehicle photo with thumbnail. It dumps the quiescent source database and copies its media; it restores into the second database and a newly created media directory. Checks compare restored bytes to source fixtures, compare PDF hashes to stored hashes, and test private storage and same/other dealership download authorization for each artifact. Photo comparisons use source bytes captured inside the temporary workspace; photos have no upload-time stored hash. No existing database or media path can be selected. The tool deletes only the workspace it created, after stopping its cluster; if stopping fails or its stopped state cannot be confirmed, it retains that workspace for manual inspection. Abrupt process termination can leave a temporary workspace or cluster requiring manual cleanup.

The fixture also captures six invented inventory audit rows (vehicle creation, photo addition, work creation, two costs and a reversal) before backup and compares all their fields after restore. In the restored database it verifies that a valid same-dealership audit insert succeeds (and rolls that test insert back), while a mismatched insert, audit update, audit delete and dealership change on the audited vehicle each fail with the expected PostgreSQL guard error. It then checks that the restored audit rows remain unchanged. These checks use transactions in the disposable restored database; they do not modify existing installations.

The reconditioning fixture uses the application services to create a synthetic
vendor, assigned task, $250.35 recorded cost, linked reversal and $40.10
replacement. It then renames the vendor, leaving the cost records' original
vendor-name snapshots intact. Every stored vendor, vendor-event, task and cost
field is captured and compared after restore, alongside inventory audit history.
The drill verifies the reversal link and control legs, a $40.10 net itemized cost,
and owner/staff/viewer access with foreign-dealership denial. These records are
internal synthetic controls, not paid invoices, accounting entries or evidence
that work was performed; this does not exercise every task or cost workflow.

The restored vendor's two events also undergo direct SQL UPDATE and DELETE
attempts, each required to fail with `Vendor events are immutable` and PostgreSQL
SQLSTATE `P0001` in a separate rolled-back transaction. All captured vendor-event
fields (including IDs, vendor/actor references, changes and timestamps) and the
remaining reconditioning records are compared to their pre-backup baseline
afterward. This checks the restored `inventory.0012_vendor_event_immutable`
row guards; privileged access, disabled triggers and `TRUNCATE` remain outside
these protections.

November 17, 2026 vendor-event guard follow-up: the isolated PostgreSQL 17.11
restore passed with all earlier fixture checks retained, and five focused
`dev.test_restore_exercise` safety tests passed. Existing databases were untouched;
this verifies two invented events, not every vendor workflow or live recovery.

The invoice upload event's complete stored fields are captured before backup
and compared after restore. Direct SQL UPDATE and DELETE must each raise
`Invoice events are immutable` with PostgreSQL SQLSTATE `P0001` in a separate
rolled-back transaction; the captured fields must still match afterward. This
checks `documents.0006_invoice_event_immutable` on the restored upload event.
The earlier authorized-download check still appends a new download event.
Privileged access, disabled triggers and `TRUNCATE` remain outside these guards.

November 17, 2026 invoice-event follow-up: the isolated PostgreSQL 17.11 restore
passed with all earlier fixture checks preserved, and five focused restore
safety tests passed. No existing database was modified. This covers one invented
restored upload event, not every invoice workflow or live recovery.

The fixture prepares a synthetic packet ZIP through the existing authenticated
`demo_packet_export` download workflow before backup. It verifies the event's
actor and bundle hash against the returned bytes, then captures every stored
packet-export-event field. After restore it compares all fields (ID, packet and
actor references, timestamp and bundle hash), checks direct SQL UPDATE/DELETE
rejection with `Packet export events are immutable` and SQLSTATE `P0001`, and
compares the fields again after the rolled-back attempts. This checks the restored
`documents.0007_packet_export_event_immutable` guard. The event records response
preparation, not confirmed delivery; historical ZIP bytes are not backed up by
this event baseline. Privileged access, disabled triggers and `TRUNCATE` remain
outside these row-level checks.

November 17, 2026 packet-export-event follow-up: the isolated PostgreSQL 17.11
restore passed with earlier checks preserved, and five restore safety tests
passed. This covers one invented export event, not every export or live recovery.

The supporting-file event baseline captures every stored field before backup.
After restore, the drill compares IDs, file/actor references, action, reason and
timestamp, attempts direct SQL UPDATE and DELETE on the restored upload event,
and compares all fields again. Each attempt must raise `Deal file events are
immutable` with PostgreSQL SQLSTATE `P0001` in a separate rolled-back transaction.
This checks `documents.0008_deal_file_event_immutable`; the existing authorized
download check still appends a download event. Privileged access, disabled
triggers and `TRUNCATE` remain outside these row-level checks.

November 17, 2026 deal-file-event follow-up: the isolated PostgreSQL 17.11 restore
passed with earlier checks preserved, and five restore safety tests passed.
Existing databases were untouched. This covers one invented restored upload
event, not every file workflow or live recovery.

After restoring, direct SQL UPDATE and DELETE are attempted on one DealEvent
from the still-uncompleted follow-on draft and the trade event from the completed
BHPH deal. All captured deal-event fields, including IDs, parent/actor references,
snapshot and timestamp, are compared with the pre-backup baseline before and
afterward. Each mutation must fail with SQLSTATE `P0001` in its own rolled-back
transaction. The draft case checks `deals.0017_deal_event_immutable`; the completed
case encounters the existing, earlier-named completion trigger first and expects
`Completed rehearsal source is frozen`. Thus it verifies rejection for both
states without claiming that both triggers executed on the completed row.

November 17, 2026 deal-event follow-up: the isolated PostgreSQL 17.11 restore
passed with all earlier checks preserved, and five focused restore safety tests
passed. Existing databases were untouched. These two invented histories do not
establish live recovery, concurrent mutation safety or protection against
privileged access, disabled triggers or `TRUNCATE`.

The drill creates and completes one assigned synthetic customer follow-up through
the application views, and records a fixed-label submission and two events using
the offline mock-message service. The simulator's separate opt-in setting is
enabled only inside the fixture; no provider or external communication is used.
Every stored activity, customer event, mock submission and mock event field is
captured and compared after restore. The restored activity is readable by the
same-dealership owner, staff and viewer but not a foreign dealership; mock status
is available only to authorized editors and foreign scope is denied. The customer
export component includes the retained activity and mock history for its owner
and excludes them from the foreign dealership's export. Mock labels are local
simulation only, not evidence of messaging, delivery or consent.

After restoring, the drill also attempts direct SQL UPDATE and DELETE on both
customer events created by the follow-up workflow. Each attempt must raise
`Customer events are immutable` with PostgreSQL SQLSTATE `P0001`, using a separate
rolled-back transaction. It then compares all captured customer-event fields
(including IDs, actor/customer references, changes and timestamps), along with
the activity and mock history, to the pre-backup baseline. This verifies the
restored guards from `customers.0010_customer_event_immutable`; privileged access,
disabled triggers and `TRUNCATE` remain outside these row-level checks.

November 17, 2026 customer-event guard follow-up: the isolated PostgreSQL 17.11
database/private-media restore passed with all earlier fixture checks retained;
all five `dev.test_restore_exercise` safety tests passed. Existing databases and
customer models/migrations were unchanged. This covers two synthetic restored
events, not live recovery, concurrent changes or every customer workflow.

The drill saves one invented staff feedback report through its local preview and
confirmation workflow, then prepares an owner-only synthetic dealership ZIP.
Before backup it checks the feedback component and its manifest hash, and matches
the package bytes to the recorded export-preparation event. After restore it
compares every report and package-event field, checks that audit updates/deletes
are rejected, and verifies report and component access by role and dealership.
Feedback saving has no separate creation-audit event. The package event records
preparation, not delivery, and the drill does not retain or restore the ZIP bytes.
No feedback is sent to a provider or external support service.

The fixture also uses the synthetic ledger services to create a standalone book, a
$10,000.25 opening, a $125.50 unapplied receipt and its linked full reversal.
It captures every book and posting field before backup and compares them after
restore, verifies the independent expected bucket totals and correction link,
and checks that direct UPDATE and DELETE on both book and posting are rejected
by their append-only guards. Rejected checks leave captured ledger history
unchanged. No payment, allocation or actual money is involved.

Using the same synthetic account, the exercise saves a monthly precomputed
illustration and selects its servicing baseline through the existing services.
It captures every stored schedule and plan field, compares them after restore,
checks the schedule digest, and verifies a fixed as-of projection: three $3,400
installments, $10,200 remaining and no eligible net receipts after reversal.
The restored coverage page is available to the owner and denied to a foreign
dealership; the checks do not change the saved servicing or ledger records.
This covers one invented schedule and baseline, not every schedule method,
servicing scenario, concurrent change or legal/financial interpretation.

A separate invented BHPH deal is completed through the rehearsal service and
opened as a second synthetic account from its frozen completion. The exercise
captures all completion, completion-packet and account-context fields, as well
as both books and their postings, and compares them after restore. It verifies
the completion and context digests, their IDs and revision, the handoff opening,
owner/viewer access and foreign-dealership denial. A rolled-back customer edit
also checks that the frozen handoff provenance remains unchanged. This is one
synthetic handoff, not verification of every completion, account or migration.

Before that completion, the drill saves an invented trade through the draft
workflow, including a rebuilt title brand, reported mileage status, allowance
and estimated payoff. It captures and compares every draft, financing proposal,
trade and deal-event field after restore. It checks that the saved trade event
and frozen completion packet retain the trade identity, brand and mileage facts,
and that the event retains the recorded allowance and payoff. This is synthetic
history, not a reviewed disclosure, ownership record or verified payoff.

The drill also completes a separate synthetic cash draft with no linked account,
records a void rehearsal and creates its follow-on draft through the existing
preview/confirmation services. It creates and completes an assigned deal
follow-up on that draft. Every void, follow-on, follow-up and follow-up-event
field is captured and compared after restore, along with the source completion,
packets, drafts and deal events. The drill checks the provenance IDs and hashes,
same-dealership access, foreign denial and PostgreSQL rejection of updates and
deletes to the void, follow-on and both restored follow-up-event records; their
fields remain unchanged after the rejected operations. Migration
`deals.0016_followup_event_immutable` adds follow-up event update/delete guards
on SQLite and PostgreSQL and must be applied to existing installations. SQLite
table rebuilds must restore those guards; privileged database access and
PostgreSQL `TRUNCATE` can bypass row-level protections. These are rehearsals,
not a legal void, new sale or customer communication.

The exercise creates a synthetic demo packet through the packet service and
captures all stored fields, including HTML, source snapshot, template version,
hashes and identifiers. After restore it compares the captured fields, checks
both hashes and the displayed research catalog version, and verifies owner
access and foreign-dealership denial. A temporary customer edit in the restored
database changes the current source while leaving the saved packet and its
downloaded bytes unchanged; the edit is rolled back.

On November 17, 2026, the expanded isolated PostgreSQL restore drill passed,
including the deal follow-up, void/follow-on provenance, deal/trade history,
feedback, package audit, reconditioning, activity, mock history, handoff,
servicing, packet, ledger, inventory audit and private-media checks. The SQLite
restore safety and follow-up run passed 21 tests; an earlier run of restore
safety, follow-up, void and follow-on completed 33 tests with four PostgreSQL-only
skips. Earlier focused runs covered feedback, reconditioning,
customer activity, the mock simulator and synthetic servicing. The records below
describe historical runs and their migration sets.

Developer verification, November 13, 2026: the expanded isolated PostgreSQL
17.11 drill passed, including the packet, existing ledger, inventory audit and
private-media checks. Five restore safety tests passed. This does not establish
recovery for all packet versions or artifacts, concurrent source changes, a live
deployment, or production backup readiness.

Developer verification, November 10, 2026: the expanded exercise passed with PostgreSQL 17.11 and the migration set at that time, including `core.0008_inventory_audit_guards`. It verified the ledger baseline, linked reversal, independently specified $10,251.25 debit and credit totals and book/posting update and delete guards; both restored audit rows and guard behavior; exact deal PDF, invoice, acquisition PDF, photo and thumbnail bytes; PDF stored hashes; and owner/foreign download access. Five `dev.test_restore_exercise` safety tests also passed. This run used a newly initialized temporary cluster, invented records, a quiescent source and a fresh destination; it did not test a live deployment, historical mismatched rows, concurrent audit/ownership or ledger races, all financial record types, every artifact type, or recovery from an interrupted restore. PostgreSQL row-level DELETE triggers do not prevent `TRUNCATE`, and privileged database access can bypass trigger protections.

This is a developer exercise, not a production backup procedure. The database dump and file copy are consistent here because no application writers are running during capture. A live system needs a coordinated database/file snapshot and orphan reconciliation. The temporary dump and files are unencrypted, and local trust authentication is confined to the private socket; neither is a production security design. Production recovery still needs encrypted off-host copies, key management and recovery, access controls, record-specific retention and legal holds, scheduling, monitoring, tested restoration of all data and private files, and documented RPO/RTO and cutover procedures. This exercise neither sets a retention period nor verifies recovery of a live deployment or external provider state.

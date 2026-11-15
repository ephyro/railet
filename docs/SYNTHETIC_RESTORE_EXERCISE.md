# Disposable synthetic database and private-file restore

Run from the project root as an unprivileged user:

```sh
.venv/bin/python dev/restore_exercise.py
# Optional: --pg-bin /path/to/compatible/postgresql/bin
```

Requires the project's Python environment and `initdb`, `pg_ctl`, `createdb`, `pg_dump`, and `pg_restore`. The default tool path is `.local/pg-integration/install/bin`. It creates a fresh, owner-only temporary workspace under `/tmp`, initializes a separate cluster with no TCP listener and a private Unix socket, creates fresh source and destination databases, migrates the source, and inserts only invented records. It uses the application services to store a synthetic deal PDF, vehicle invoice, acquisition PDF, and vehicle photo with thumbnail. It dumps the quiescent source database and copies its media; it restores into the second database and a newly created media directory. Checks compare restored bytes to source fixtures, compare PDF hashes to stored hashes, and test private storage and same/other dealership download authorization for each artifact. Photo comparisons use source bytes captured inside the temporary workspace; photos have no upload-time stored hash. No existing database or media path can be selected. The tool deletes only the workspace it created, after stopping its cluster; if stopping fails, it retains that workspace for manual inspection. Abrupt process termination can leave a temporary workspace or cluster requiring manual cleanup.

The fixture also captures both invented inventory audit rows (vehicle creation and photo addition) before backup and compares all their fields after restore. In the restored database it verifies that a valid same-dealership audit insert succeeds (and rolls that test insert back), while a mismatched insert, audit update, audit delete and dealership change on the audited vehicle each fail with the expected PostgreSQL guard error. It then checks that the restored audit rows remain unchanged. These checks use transactions in the disposable restored database; they do not modify existing installations.

The fixture also uses the synthetic ledger services to create one book, a
$10,000.25 opening, a $125.50 unapplied receipt and its linked full reversal.
It captures every book and posting field before backup and compares them after
restore, verifies the independent expected bucket totals and correction link,
and checks that direct UPDATE and DELETE on both book and posting are rejected
by their append-only guards. Rejected checks leave captured ledger history
unchanged. No payment, allocation or actual money is involved.

The exercise creates a synthetic demo packet through the packet service and
captures all stored fields, including HTML, source snapshot, template version,
hashes and identifiers. After restore it compares the captured fields, checks
both hashes and the displayed research catalog version, and verifies owner
access and foreign-dealership denial. A temporary customer edit in the restored
database changes the current source while leaving the saved packet and its
downloaded bytes unchanged; the edit is rolled back.

Developer verification, November 13, 2026: the expanded isolated PostgreSQL
17.11 drill passed, including the packet, existing ledger, inventory audit and
private-media checks. Five restore safety tests passed. This does not establish
recovery for all packet versions or artifacts, concurrent source changes, a live
deployment, or production backup readiness.

Developer verification, November 10, 2026: the expanded exercise passed with PostgreSQL 17.11 and the current migration set, including `core.0008_inventory_audit_guards`. It verified the ledger baseline, linked reversal, independently specified $10,251.25 debit and credit totals and book/posting update and delete guards; both restored audit rows and guard behavior; exact deal PDF, invoice, acquisition PDF, photo and thumbnail bytes; PDF stored hashes; and owner/foreign download access. Five `dev.test_restore_exercise` safety tests also passed. This run used a newly initialized temporary cluster, invented records, a quiescent source and a fresh destination; it did not test a live deployment, historical mismatched rows, concurrent audit/ownership or ledger races, all financial record types, every artifact type, or recovery from an interrupted restore. PostgreSQL row-level DELETE triggers do not prevent `TRUNCATE`, and privileged database access can bypass trigger protections.

This is a developer exercise, not a production backup procedure. The database dump and file copy are consistent here because no application writers are running during capture. A live system needs a coordinated database/file snapshot and orphan reconciliation. The temporary dump and files are unencrypted, and local trust authentication is confined to the private socket; neither is a production security design. Production recovery still needs encrypted off-host copies, key management and recovery, access controls, record-specific retention and legal holds, scheduling, monitoring, tested restoration of all data and private files, and documented RPO/RTO and cutover procedures. This exercise neither sets a retention period nor verifies recovery of a live deployment or external provider state.

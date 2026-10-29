# Isolated PostgreSQL integration environment

## Outcome

The original QEMU VM remains offline in the current execution environment: `/dev/kvm` is unavailable, SSH on loopback 2223 refuses connections, and the signed-in account cannot access the host Docker socket. Neither Docker group membership nor the VM disk was changed. No privileged host installation was performed.

A separate PostgreSQL **17.11** instance was built from [official source](https://www.postgresql.org/ftp/source/v17.11/) after checking its published SHA-256. Build, installation, cluster, socket, logs, backups and media all live under ignored `.local/pg-integration/`. This is an optional developer toolchain, not production hosting or a bundled PostgreSQL distribution.

The cluster listens on **no TCP addresses**. It uses an owner-only directory/socket (0700) on a local Unix socket, port identifier 55432, with local trust authentication inside that filesystem boundary and host authentication rejected. Trust here is not a recommendation for a shared or production server. The cluster owner is a superuser, as needed to create isolated test databases; do not expose its socket or use it with real data.

## Existing checkout commands

From the project root:

```sh
./dev/postgres.sh status
./dev/postgres.sh start
./dev/postgres.sh check
./dev/postgres.sh migrate --noinput
./dev/postgres.sh test --noinput
./dev/postgres.sh stop
```

`start` only starts an already initialized cluster; it never resets or initializes data. `stop` stops the integration database and affects any local preview using it. The helper explicitly sets PostgreSQL mode, avoiding an inherited SQLite opt-in. Set `RAILET_PG_BIN` to an existing compatible PostgreSQL tools directory when using a different local installation. It does not modify shell startup or system services.

On another workstation, install or build PostgreSQL 17 through your preferred trusted mechanism; initialize a separate development-only cluster under `.local/pg-integration/data`, create `.local/pg-integration/socket` owner-only, and create database `railet_integration` owned by your current Unix username. Do not point this helper at production data. The cluster used here was initialized with UTF-8, `--no-locale`, `--auth-local=trust`, `--auth-host=reject`, and started with empty `listen_addresses` and `unix_socket_permissions=0700`. No cluster initialization is hidden inside test commands.

## Migrations and verification

Every current migration applied successfully to the fresh PostgreSQL integration database, including pending feedback, retained packets/export auditing, draft archival/follow-ups and the new finance demo. **This does not migrate or validate the original VM's existing data.** Existing-data upgrade/cutover remains a separate exercise.

The full PostgreSQL suite passed **237 tests with no skips** in 104.155 seconds. This includes the previously skipped concurrency tests and new tests for feedback retry, packet retry, archive retry, follow-up retry, archive-versus-packet ordering, ledger opening/receipt retry, competing reversals and database insert/append-only guards. A later focused finance rerun passed all 21 tests without skips after the consistent journal-read transaction was added. System and migration drift checks passed.

Firefox exercised a fresh synthetic PostgreSQL-backed preview at loopback port 8003: saved packet/artifact/hash-verified ZIP, private feedback preview/save, follow-up/Home/completion, archive/restore with unchanged older artifact, full history, private PDF upload/exact-byte download, and ledger opening/two receipts/linked correction through signed preview/confirm screens. Ledger detail layouts were checked at 1440,390,320 pixels. These are developer checks, not staff validation.

The temporary preview launcher and its generated account password remain private under `.local/`. The regular supported app source/configuration is the project root. No demonstration password is published. The separate proprietary website stays outside DMS source exports.

## Restore exercise

A `pg_dump` of the quiescent synthetic integration database and a copy of its private-media directory were restored into a **different** PostgreSQL database and media directory, leaving the source intact. All rows were compared across 15 selected business tables, including ledger and retained packet rows; retained HTML hashes and the private PDF bytes matched. The restored journal trigger rejected an UPDATE. Backup files remain ignored and owner-readable. Browser verification preceded the snapshot; no concurrent production traffic or external provider events were involved.

This verifies that particular synthetic database/media snapshot and restored trigger behavior. It does not establish production backup scheduling, encryption, remote storage durability, key recovery, legal holds, RPO/RTO, live cutover, or operation against restored credentials. Those remain release gates.

The private evidence is under `.local/pg-integration/` (`browser-results.json`, `file-browser-results.json`, `restore-results.json`, logs and backups). No source push, production deployment or real customer import occurred.


Schedule/method verification follow-up: the full PostgreSQL suite ran 261 tests, with 260 passing and one stale review-row assertion failing after insertion of the new method row. That assertion was updated; all 23 review/schedule workflow tests then passed. The earlier focused finance/proposal/document run passed 95 tests. No second full-suite run was performed. Browser checks verified retained draft method selection, monthly illustration default, both calculation profiles and responsive schedule views. Evidence is private under `.local/schedule-review/`. These checks use synthetic data and do not establish legal or staff validation.


BHPH workspace verification: the complete PostgreSQL suite passed **273 tests** in 124.795 seconds, with no skips. Synthetic account/browser evidence is retained privately under `.local/account-review/`.


October 26 draft-opening verification: the complete PostgreSQL suite passed 285 tests in 111.229 seconds with no skips, including same-key and distinct-key concurrent opening cases. Ten focused SQLite tests passed. Synthetic browser checks covered draft → reviewed opening → account navigation at 1440/390/320 pixels; no outer page overflow was found. These are developer checks, not staff or legal validation. Private evidence: `.local/draft-opening-review/`.


Account-search verification (October 26, 2026): the full PostgreSQL suite passed 293 tests in 113.799 seconds with no skips; 25 focused PostgreSQL checks and eight focused SQLite checks passed. Browser checks exercised stock search, linked/unlinked scopes, advanced-rule editing, private saved views and account navigation at 1440/390/320 pixels without page overflow. These are synthetic developer checks; no production workload or staff validation is claimed. Private evidence: `.local/account-search-review/`.


Account-export verification (October 26, 2026): the full PostgreSQL suite passed 303 tests in 107.854 seconds with no skips. Nine focused export tests also passed on SQLite. Verification includes independent expected journal totals, exact ZIP/manifest hashes, linked reversals, stored schedule preservation, CSV formula safety, authorization, failed-audit rollback, HEAD behavior, database audit immutability and real PostgreSQL row-lock exclusion during capture. Browser checks downloaded a synthetic ZIP, checked all file hashes, verified visible export history and checked 1440/390/320-pixel layouts without page overflow. This is developer verification, not staff or legal validation. Private evidence: `.local/account-export-review/`.


Payment-register verification (October 26, 2026): the full PostgreSQL suite passed 312 tests in 111.993 seconds without skips. Nine focused tests passed on each PostgreSQL and SQLite. Checks cover independent receipt/correction totals, negative range activity, recorded/effective date separation, daylight-saving boundaries, single-query capture, dealership isolation, date validation, size limits and pagination totals. Browser checks verified the synthetic $74.50 net range, date switching and validation at 1440/390/320 pixels without outer overflow. This is developer verification, not staff or legal validation. Private evidence: `.local/payment-register-review/`.


Customer-address verification (October 26, 2026): the final PostgreSQL suite passed 324 tests in 112.813 seconds without skips. Focused checks cover optional/partial entry, international text, omitted-field compatibility, explicit clearing, revision conflicts, authorization, escaped display, existing-data migration, visible packet previews, frozen buyer/co-buyer addresses and versioned account exports. Twenty-three SQLite address/snapshot checks and nine SQLite address/migration checks passed. Browser checks confirmed canonical reuse, preservation of old packet addresses after a later edit and 1440/390/320-pixel layouts. An outdated historical migration-test target was corrected before the successful final run. These are synthetic developer checks, not staff, postal or legal validation. Private evidence: `.local/customer-address-review/`.

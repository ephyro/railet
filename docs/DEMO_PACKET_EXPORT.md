# Portable demo packet export

Open an existing saved demo packet and expand **Export this demo packet**. The explanation identifies the exact scope, private-file handling, lack of encryption, and audit record before the user selects **Download demo packet ZIP**.

## Contents

- `DEMO-summary.html`: exact retained UTF-8 HTML bytes, including demonstration markings and embedded print styles. It is not regenerated using the current template.
- `snapshot.json`: captured JSON facts, original template version, capture time, packet/deal IDs, creator account ID and source fingerprint. These are stable identifiers, not a lookup into current customer profiles.
- `README.txt`: scope, evaluation-only warning, instructions and limitations.
- `manifest.json`: byte length and SHA-256 for the other three files, plus export format/version and demonstration marker. The manifest does not hash itself.

Every export of the same retained packet produces the same ZIP bytes: content ordering, member timestamps, modes and compression settings are fixed. No current customer/vehicle edits, archive changes or export-time timestamps are added to the bundle. Manifest hashes detect accidental changes, not malicious replacement, authorship or digital signatures.

This is **one demonstration packet**, not a complete deal export, complete data export, signed-document archive, or database/media backup. Uploads, signed files, photographs, complete history and later changes are excluded. There is no import/restore tool. The ZIP is not encrypted; recipients must handle it privately. No cloud reporting or network integration is involved in preparing it. It remains behind the development demo-packet gate.

## Controls

The authenticated route scopes the packet to the member's dealership before preparing bytes. Viewers may export a packet they can already read. GET prepares a ZIP and writes a separate `DemoPacketExportEvent` with actor, time, packet and bundle hash in the same transaction; audit failure prevents release of the response. This records preparation of an authorized response, not proof of completed download or delivery. HEAD returns the same attachment metadata with no body and no export event. POST is rejected.

Stored HTML and source JSON fingerprints must match before packaging; failures return 409 without creating an export event. Member paths are fixed and contain no names, record-derived paths or traversal sequences. Individual prepared members are capped at 8 MiB to reject unexpectedly oversized stored artifacts. This is a bound on export members, not a measured process-memory guarantee. Private no-store, attachment disposition, nosniff and sandbox headers apply.

The export does not mutate the packet, draft, money, parties or template. Audit rows are protected from application deletion via this slice, not privileged direct database mutation. Record-specific retention/legal-hold policy and full restore verification remain outstanding.

## Verification

Nine focused tests cover exact artifact/data bytes and independent manifest verification, deterministic exports after draft changes, authorization before packaging, viewer access, tampered HTML/data rejection, HEAD/POST behavior, disabled gate, audit failure and size bounds. The relevant export/packet/history/lifecycle suite passed 35 tests. Django system and migration drift checks passed.

The new migration is `documents.0003_demopacketexportevent`. It was applied to the isolated synthetic SQLite preview only; the primary VM and PostgreSQL integration remain unavailable. Firefox verified the explanatory controls, authenticated attachment response, exact four filenames, independent member hashes and demonstration markings. Export controls were checked at 1440,390,320 pixels with no horizontal overflow. These checks use that separate synthetic local database, not PostgreSQL or staff usability testing. No production deployment or public push is performed.

## PostgreSQL integration follow-up

The subsequent isolated PostgreSQL 17.11 integration completed: all current migrations applied to a fresh synthetic database, the complete DMS suite passed 237 tests with no skips, and browser workflows passed on PostgreSQL. This supersedes the earlier lack of PostgreSQL runtime evidence for this source slice. The original offline VM and its existing data remain untouched and unverified for upgrade. See [POSTGRES_INTEGRATION.md](POSTGRES_INTEGRATION.md) for environment, concurrency, browser and synthetic restore evidence and limits.

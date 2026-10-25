# Frozen demonstration deal packets

This is a development-only summary workflow, not reviewed Florida paperwork or production deal finalization. It introduces no statutory form, required disclosure language, lending calculation, signature, payment, tax rule, or retention/deletion rule. Existing legal/financial gates remain in force. `DEMO_PACKETS_ENABLED` follows DEBUG; routes fail closed when disabled, including before authentication.

## Workflow

Open a saved draft and choose **Demo packets**. Review the saved vehicle, parties, worksheet, active trade and selected financing proposal. Missing/unverified fields are preserved and displayed as human reminders rather than legal requirements. Missing facts do not prevent a clearly marked synthetic demonstration artifact from being created. Complete fields are not proof of evidence or legal readiness.

**Save demo packet** preserves a versioned JSON snapshot and the exact rendered HTML in the database, with creator, capture timestamp, source fingerprint, template version and artifact SHA-256. There are no replace/edit/delete packet endpoints. The current template is `demo-summary-v2`, with snapshot schema 2 recording active/archived draft state. Existing version-1 artifacts remain byte-for-byte retained; future changes must use a new template version. Existing packets are read from their stored HTML rather than regenerated. Related records are captured as values, not rendered through live references. Money values use Decimal/string formatting and reuse the existing draft worksheet arithmetic; the result remains a draft estimate, not a statutory amount-financed or payoff disclosure.

The HTML carries explicit demonstration markings, including print styling and no signature areas. It can be opened and printed or saved as PDF through the browser; this is **not** server-generated PDF output. No supporting PDFs, uploaded images, contracts, or signed artifacts are embedded. Template CSS is stored with the artifact; it has no external dependencies. The application shell may change independently of the stored artifact.

## Authorization, consistency and retries

Owners/staff create; read-only dealership members can inspect saved packets and the current preview. All routes scope the parent deal and packet on the server. Invalid cross-dealership live vehicle/customer references fail closed during preview or creation. Artifact authorization uses the saved packet's scoped parent, then verifies the stored HTML hash before returning bytes. Responses are private/no-store. Stored HTML uses a sandboxed CSP that disallows scripts, external resources, forms, and framing. Django escapes source text at initial rendering.

A signed 30-minute token binds preview to actor, dealership, deal, source fingerprint, and a fresh UUID. The creation service checks current membership and permissions. Under a transaction it locks the dealership, parent draft, vehicle and canonical customer rows in a stable order before capturing facts; parent locking coordinates active trade/proposal writes through current application interfaces. Source changes after preview return 409 with a fresh preview, without saving a packet. Concurrent PostgreSQL behavior still requires runtime verification.

A unique deal/creation key protects retries. Retrying a successful token returns its original artifact even after source changes. Reusing that key with a different source or actor fails. Packet insertion failure leaves no partial artifact or financial changes. The saved creator/time provide creation provenance; there is no new immutable audit infrastructure or per-read delivery log.

## Integrity and limitations

The hash detects accidental artifact changes; a privileged database writer can modify both content and hash. Application interfaces are append-only, not a database-level immutability guarantee. Customer contact details and structured title/mileage are frozen as recorded; later changes do not repair past artifacts. Free-text deal/trade notes, costs, unrelated proposals, and uploaded files are intentionally not included.

Before real documents: obtain rights to reviewed forms, research applicable effective dates and required evidence, implement approved applicability and version rules, retention/legal holds, export, backup restoration, access/security review and finalization state transitions. No production readiness is claimed. Database backups must include these database-resident artifacts; no restore drill has been performed for this feature. Live signing and legally effective finalization remain disabled.

## Verification

Twelve focused local tests cover preview/save separation, independently stated worksheet reference value, frozen facts and HTML after source/template changes, idempotent retry after source edits, stale/tampered/expired preview rejection, dealership/role boundaries, malformed cross-dealership relations, disabled gate, HTML escaping, artifact hash failure, zero versus unknown, render-failure rollback, no deal revision/money/event mutation, CSRF/method checks and HEAD handling.

Full local SQLite suite: 177 tests run, passed with 6 backend-specific skips. Django system and migration drift checks passed. This does not verify PostgreSQL row locking or concurrency. The development VM remains unavailable in this execution environment; migration `documents.0002_demodealpacket` and the preceding feedback migration have not been applied there. An isolated ignored SQLite database is used for local Firefox workflow/layout checks, not an import of dealership data. Firefox verified navigation from the draft toolbar, preview/save/open, visible demonstration markings, and preview/artifact layouts at 1440, 390 and 320 pixels without page overflow. The first narrow preview overflow was corrected with scoped wrapping styles. Feedback preview-confirm-save was also verified in that isolated database. These are developer checks, not staff validation, PostgreSQL verification, a print/PDF inspection, or backup restoration.

## Portable export

Existing saved packets can now be downloaded as a private ZIP of exact HTML, snapshot JSON, README and hash manifest. Export preparation is audited independently of packet creation. This is a single-packet transfer, not full data export or a backup. See [DEMO_PACKET_EXPORT.md](DEMO_PACKET_EXPORT.md) for controls, exclusions, migration and checks.

## PostgreSQL integration follow-up

The subsequent isolated PostgreSQL 17.11 integration completed: all current migrations applied to a fresh synthetic database, the complete DMS suite passed 237 tests with no skips, and browser workflows passed on PostgreSQL. This supersedes the earlier lack of PostgreSQL runtime evidence for this source slice. The original offline VM and its existing data remain untouched and unverified for upgrade. See [POSTGRES_INTEGRATION.md](POSTGRES_INTEGRATION.md) for environment, concurrency, browser and synthetic restore evidence and limits.


New packets use demo-summary-v3 / snapshot schema 3 and freeze the proposed interest method. Earlier retained artifacts are not regenerated.

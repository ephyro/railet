# Private local feedback

The Feedback module records workflow problems and improvement ideas inside the current installation. It does not send to Ephyro, GitHub, email, or any support provider. It makes no support response or production-readiness promise. Use synthetic examples only in this development build.

## Workflow

Use **Help & feedback** from the sidebar or mobile page footer. Describe the problem, explicitly acknowledge removing private information, and preview the report. Previewing does not create a database record. The preview displays the submitted text, account identity, destination, visibility, and stored metadata. Edit returns the original fields; confirming saves a numbered local report. No attachments, URLs, screenshots, customer references, browser data, or diagnostics are collected automatically.

Reports are visible to their author and dealership owners. Staff and read-only members can submit and read their own reports; this permission grants no edits to inventory, customers, deals, or money. Owners see dealership reports only. Lists paginate 25 at a time. Saved report text is not editable through this slice.

The form does **not** automatically redact sensitive free text. Authors must use invented examples. The private preview token is signed, not encrypted, and submitted only in POST bodies; the signed data is not put in query strings or logs by this module. Signing prevents modification and binds previews to the account/dealership; it is not a confidentiality mechanism. Pages use private no-store responses. Any future diagnostic integration must separately review sanitization and infrastructure logging.

## Integrity and boundaries

A 30-minute signed preview is required for confirmation. Confirmation revalidates the payload and ignores unrelated posted fields. A unique dealership/author/submission key makes retries return the original report. A changed version of an already saved key produces HTTP 409 without overwriting it. The transaction locks the dealership row before creation to serialize concurrent confirmation on PostgreSQL. No external network action or financial posting occurs.

CSRF protection, server-side membership scoping, Django autoescaping, bounded fields, explicit accepted choices, and attachment rejection apply. Acknowledging privacy is not evidence that a report is free of private information. No automatic deletion, public posting, telemetry, security incident workflow, external support integration, status tracking, or response SLA is implemented. Administrators control retention; record-specific legal holds/retention must be defined before any live sensitive intake.

## Installation and verification

Apply `feedback.0001_initial`. Development Compose, the VM sync allowlist, and the staging Dockerfile include the module. A running development web container needs recreation to pick up the new source mount; existing database/upload volumes must be retained.

Twelve focused local tests pass: preview/save separation, signed-field trust, duplicate confirmation, conflict preservation, errors and privacy acknowledgement, expired/tampered tokens, actor/dealership binding, author/owner access, viewer submission, edit round trip, upload rejection, HTML escaping/private cache headers, authentication, methods, and CSRF.

The full local SQLite suite completed: 165 tests run, passing with 6 backend-specific skips. SQLite results do not establish PostgreSQL concurrency behavior.

The current development VM is offline (SSH loopback port 2223 refuses connections), and this execution environment lacks `/dev/kvm`. Therefore this change has not yet been migrated or verified against that PostgreSQL VM. Prior module PostgreSQL results do not verify this module. Apply the migration and verify concurrent report confirmation and the complete browser workflow there before treating this handoff as integrated. No production deployment or public push occurred.

Follow-up during demo packet development: the feedback preview/confirm/save workflow was verified in Firefox against a separate synthetic local SQLite database. PostgreSQL integration, concurrency and development-VM migration remain outstanding.

## PostgreSQL integration follow-up

The subsequent isolated PostgreSQL 17.11 integration completed: all current migrations applied to a fresh synthetic database, the complete DMS suite passed 237 tests with no skips, and browser workflows passed on PostgreSQL. This supersedes the earlier lack of PostgreSQL runtime evidence for this source slice. The original offline VM and its existing data remain untouched and unverified for upgrade. See [POSTGRES_INTEGRATION.md](POSTGRES_INTEGRATION.md) for environment, concurrency, browser and synthetic restore evidence and limits.

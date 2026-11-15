# Private local feedback

The Feedback module records workflow problems and improvement ideas inside the current installation. It does not send to Ephyro, GitHub, email, or any support provider. It makes no support response or production-readiness promise. Use synthetic examples only in this development build.

Source review: November 13, 2026, against feedback views/forms/models/export,
base/staging settings, routes and the account-menu template. No runtime tests or
VM upgrade were repeated; the verification counts below describe earlier slices.

## Workflow

Use **Help & feedback** from the signed-in account menu in the top bar. Describe the problem, explicitly acknowledge removing private information, and preview the report. Previewing does not create a database record. The preview displays the submitted text, account identity, destination, visibility, and stored metadata. Edit returns the original fields; confirming saves a numbered local report. No attachments, URLs, screenshots, customer references, browser data, or diagnostics are collected automatically.

Reports are visible to their author and dealership owners. Staff and read-only members can submit and read their own reports; this permission grants no edits to inventory, customers, deals, or money. Owners see dealership reports only. Lists paginate 25 at a time. Saved report text is not editable through this slice.

The form does **not** automatically redact sensitive free text. Authors must use invented examples. The private preview token is signed, not encrypted, and submitted only in POST bodies; the signed data is not put in query strings or logs by this module. Signing prevents modification and binds previews to the account/dealership; it is not a confidentiality mechanism. Normal feedback responses pass through `never_cache`; this is not a guarantee for unexpected exception responses. The feedback views do not set the marker used by `PrivateErrorCacheMiddleware` for private 500 responses. Error/logging behavior remains a security-review item. Any future diagnostic integration must separately review sanitization and infrastructure logging.

## Integrity and boundaries

A 30-minute signed preview is required for confirmation. Confirmation revalidates the payload and ignores unrelated posted fields. A unique dealership/author/submission key makes retries return the original report. A changed version of an already saved key produces HTTP 409 without overwriting it. The transaction locks the dealership row before creation to serialize concurrent confirmation on PostgreSQL. No external network action or financial posting occurs.

CSRF protection, server-side membership scoping, Django autoescaping, bounded fields, explicit accepted choices, and attachment rejection apply. Acknowledging privacy is not evidence that a report is free of private information. No automatic deletion, public posting, telemetry, security incident workflow, external support integration, status tracking, or response SLA is implemented. No administrator retention or legal-hold management workflow is implemented. The [record-specific retention/hold proposal](FLORIDA_RETENTION_RESEARCH.md) is documentation only; operational review and enforcement remain open before live sensitive intake. Feedback intake is membership-scoped but has no DEBUG feature gate, including in staging; that availability does not authorize real-data use.

## Historical installation and verification (October 2026)

The original slice introduced `feedback.0001_initial`; for the current checkout review and apply the complete migration set with the selected environment's documented `manage.py migrate` command, preserving existing database and private-file volumes. Development Compose, the VM sync allowlist, and the staging Dockerfile include the module. A running development web container needs recreation to pick up the new source mount; existing database/upload volumes must be retained.

The historical run reported twelve focused local tests passing: preview/save separation, signed-field trust, duplicate confirmation, conflict preservation, errors and privacy acknowledgement, expired/tampered tokens, actor/dealership binding, author/owner access, viewer submission, edit round trip, upload rejection, HTML escaping/private cache headers, authentication, methods, and CSRF.

The full local SQLite suite completed: 165 tests run, passing with 6 backend-specific skips. SQLite results do not establish PostgreSQL concurrency behavior.

At that check the development VM was offline (SSH loopback port 2223 refused connections), and the environment lacked `/dev/kvm`; the change had not been migrated or verified against that PostgreSQL VM. No production deployment or public push occurred for that slice.

Follow-up during demo packet development: the feedback preview/confirm/save workflow was verified in Firefox against a separate synthetic local SQLite database. At that point PostgreSQL integration and the development-VM migration remained outstanding.

## PostgreSQL integration follow-up

The subsequent isolated PostgreSQL 17.11 integration completed: migrations existing then applied to a fresh synthetic database, the then-current DMS suite passed 237 tests with no skips, and browser workflows passed on PostgreSQL. This supersedes the earlier lack of PostgreSQL runtime evidence for this source slice, not verification of later changes. The original offline VM and its existing data were not verified for upgrade. See [POSTGRES_INTEGRATION.md](POSTGRES_INTEGRATION.md) for environment, concurrency, browser and synthetic restore evidence and limits. A separate owner-only, DEBUG-gated synthetic dealership ZIP includes dealership feedback, unredacted. Its component in `feedback/export.py` has no standalone endpoint or delivery audit; the ZIP orchestrator audits package preparation, not confirmed receipt. Downloaded bytes leave application storage under the recipient's control; there is no automatic external support submission, encryption or redaction. This export gives owners access to same-dealership reports, not unrelated dealerships.

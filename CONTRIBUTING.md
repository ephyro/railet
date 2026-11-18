# Contributing to Railet

Thanks for helping make dealership software clearer. Railet is an early development project; use original work and synthetic data throughout.

## Start with a task

Read [AGENTS.md](AGENTS.md), the [development guide](docs/DEVELOPMENT.md), [product plan](docs/RAILET_PLAN.md), and [remaining work backlog](docs/REMAINING_WORK.md). For a guided tour of the current prototype, follow the [synthetic BHPH end-to-end walkthrough](docs/BHPH_DEMO_WALKTHROUGH.md) (`vehicle → customer → BHPH deal → draft review → completion rehearsal → BHPH account → test receipt`). Discuss substantial architecture, financial, document, security, or scope changes before implementation. Small fixes can go directly to a pull request. An issue does not guarantee someone will implement it or a support response time.

### Current contributor starting points (synthetic workflows only)

- **Walkthrough and responsive UX checks:** Run the [synthetic BHPH walkthrough](docs/BHPH_DEMO_WALKTHROUGH.md), reconditioning queue, or customer follow-up queue on desktop and mobile widths (`1440px`, `390px`, `320px`). Fix concrete keyboard focus, label, contrast, or layout issues without removing required notices or safety gates.
- **Scoped reports and formula-safe exports:** Help define date, status, correction, and role semantics for remaining synthetic reports (such as itemized reconditioning costs, BHPH activity, or time-to-sale once sale dates exist), including cross-dealership isolation and CSV formula-injection tests.
- **Isolated sandbox adapters (no live traffic):** Contribute to local-only test harnesses—such as the offline [DocuSeal rehearsal](docs/DOCUSEAL_REHEARSAL.md) or future sandbox messaging adapters—verifying webhook authentication, replay/idempotency handling, and notification suppression with `@example.invalid` identities only.
- **Backup, restore, and isolation verification:** Expand automated tests and scripts for dealership isolation, append-only ledger/cost triggers, and database plus private-media backup/restore drills.

Use Discussions for workflow questions and ideas. For bugs, explain what you expected, what happened, and how to reproduce it with invented records. Keep vulnerability details in [private security reporting](SECURITY.md).

## Pull requests

1. Keep the change focused and explain the dealership task it improves.
2. Preserve server-side permissions, dealership isolation, financial integrity, and historical records.
3. Add meaningful checks for the risk involved. Financial, authorization, concurrency, and private-file changes require explicit verification; a simple wording fix does not need redundant tests.
4. Report what you actually tested and what remains uncertain. Never describe developer checks as staff usability validation.
5. Preserve SPDX/license notices and document new dependencies and their licenses.
6. Sign off commits with `git commit -s` only if you can certify the [Developer Certificate of Origin 1.1](https://developercertificate.org/).

Contributions are accepted under MPL 2.0 unless explicitly agreed otherwise before submission. You retain your copyright; no copyright assignment or proprietary relicensing permission is implied. Do not include code or assets you lack permission to contribute.

## Privacy and regulated workflows

Never submit actual customer records, credit reports, contracts, credentials, session captures, database dumps, or private vendor HTML/assets. Replace identifying information before reporting an issue; blacking out one field is not sufficient if the remaining screenshot identifies someone. Automated agents must follow AGENTS.md.

Live signing, payments, credit pulls, servicing, legal forms, and lending calculations require their documented review and integration gates. Safe mock work can continue with synthetic records. Do not represent a feature as legally compliant because tests pass.

## Community and business direction

Be respectful, discuss the work, and avoid harassment or personal attacks. The plan is an MPL community product with future services and separately licensed enterprise extensions. Essential security, reviewed basic documents, core BHPH, and complete data export belong in Community as they are built. Pricing and roadmap ideas are proposals, not promises.

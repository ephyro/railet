# Contributing to Railet

Thanks for helping make dealership software clearer. Railet is an early development project; use original work and synthetic data throughout.

## Start with a task

Read [AGENTS.md](AGENTS.md), the [development guide](docs/DEVELOPMENT.md), and [product plan](docs/RAILET_PLAN.md). Discuss substantial architecture, financial, document, security, or scope changes before implementation. Small fixes can go directly to a pull request. An issue does not guarantee someone will implement it or a support response time.

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

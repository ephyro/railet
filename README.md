# Railet

**A clearer workspace for independent dealerships.**

Railet is an open-source dealership management system by [Ephyro](https://github.com/ephyro), started by a Florida independent dealer who also runs a buy-here-pay-here operation. The goal is practical: enter information once, find what you need, and complete dealership work without fighting the software.

We're building in public and welcome developers, dealership staff, and IT operators who want to help shape it.

> **Early development — synthetic data only.** This is a working prototype, not a production DMS. Do not enter actual customer information or use it for live transactions. Contracts, lending calculations, servicing, live payments, electronic signing, MFA, and production acceptance remain outstanding. Public source availability does not establish regulatory compliance.

## What works today

- Inventory with stock/VIN search, title brands, odometer details, costs, private photos, and duplicate VIN review.
- Shared customer records reused across buyers, co-buyers, and draft deals.
- A deal desk with visible deal type, inline vehicle/customer entry, pricing, trades, financing proposals, monthly payment illustrations, saved history, and a read-only review.
- Automatic 2026 Florida draft tax estimates using the purchaser’s registration county, with explicit trade/fee controls and manual review for special cases.
- Synthetic BHPH accounts with opt-in monthly installment coverage, status filters, unapplied receipts, linked reversals, daily payment summaries, private account exports, and printable demo receipts.
- Private supporting PDFs with authorized downloads, archive/restore, and upload retry protection in development.
- Reusable filters, sorting, pagination, and personal saved views.
- Dealership scoping, owner/staff/viewer roles, revision checks, and transactional change records.

Draft amounts and payment illustrations are estimates. Florida tax estimation has a narrow researched 2026 profile; manual overrides require a reason. Professional tax/legal review remains required before live use. Monthly payment illustrations are not APR disclosures or contractual daily accrual; synthetic receipts remain unapplied and do not reduce principal. Saving a draft does not sell or reserve a vehicle, create a contract or loan, or record money received. Supporting PDFs are stored as uploaded; they are not scanned or verified. Audit records are not protected from privileged direct database modification.

## Try the development build

You need Docker and Docker Compose. From a checkout:

```sh
cp .env.example .env
# Edit .env and replace POSTGRES_PASSWORD with a random local password.
docker compose up --build -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo
```

Open http://localhost:8000. Sign in as `demo` using the password you chose at the prompt (at least 12 characters). There is no default password. Use invented information only.

Code edits reload during development. Stop with `docker compose down`; database and private upload volumes persist. Adding `-v` deletes those volumes.

See [development setup](docs/DEVELOPMENT.md) for local Python, tests, migrations, and architecture. Optional [VM setup](docs/DEVELOPMENT_VM.md) and [staging rehearsal](docs/STAGING_VM.md) are development tools, not a production deployment guide.

For the synthetic workflows, see the [BHPH walkthrough](docs/BHPH_DEMO_WALKTHROUGH.md), [deal desking and Florida tax scope](docs/FLORIDA_DRAFT_TAX.md), and [staff usability session](docs/STAFF_WORKFLOW_TEST.md).

## Help build it

Start with [CONTRIBUTING.md](CONTRIBUTING.md). Useful contributions include:

- Dealer feedback: describe a specific task, the friction, and what a clear workflow would look like.
- Accessibility and usability improvements, with keyboard and small-screen checks.
- Reproducible bug reports and focused fixes using synthetic records.
- Installation, testing, documentation, and backup/restore tooling.
- Independent review of authorization, data integrity, and module boundaries.

Use [Discussions](https://github.com/ephyro/railet/discussions) for ideas and collaboration, and [Issues](https://github.com/ephyro/railet/issues) for reproducible bugs and scoped improvements. Never post customer records, contracts, credentials, account screenshots, or private vendor captures. Report vulnerabilities through [private security reporting](https://github.com/ephyro/railet/security/advisories/new).

## Direction

The next major steps are complete deal workflows and reviewed document snapshots, followed by a reviewed BHPH subledger and servicing. Security hardening, recovery drills, staff feedback, and appropriate legal/financial review are prerequisites for live use. These are roadmap items, not delivery promises.

Railet uses Django, PostgreSQL, server-rendered templates, and small JavaScript modules. It is one modular product: inventory, customers, deals, documents, and later servicing/finance each own their records. Read the [product and engineering plan](docs/RAILET_PLAN.md) for scope, compliance research, open questions, and release gates.

## Open source and a sustainable business

The community source is licensed under [MPL 2.0](LICENSE). The plan keeps essential security, reviewed basic documents, core BHPH functions, and complete data export in Community as those capabilities are built.

Future revenue is intended to come from implementation, migration, training, support, managed hosting, and separately licensed enterprise extensions. Paid services and enterprise offerings are planned; there is no production service or pricing commitment here. Contributors retain their copyright; contributions do not imply copyright assignment or permission to move community work into closed files.

See [third-party notices](THIRD_PARTY_NOTICES.md) for dependencies. The Railet and Ephyro names identify this project; the software license does not grant trademark rights.

## Private feedback

**Help & feedback** lets members preview and save workflow reports privately in their installation. Authors and dealership owners can view them; nothing is sent to Ephyro or GitHub. No attachments or diagnostics are collected. Use synthetic examples and remove private information yourself. See [feedback scope and verification](docs/FEEDBACK.md); the new module requires migration and its PostgreSQL VM integration check remains outstanding.

Saved drafts also offer **Demo packets** in development: preview a synthetic summary and preserve its facts and exact HTML for later inspection. No legal form, transaction finalization, loan, payment, or signature is created. See [demo packet scope and verification](docs/DEMO_PACKETS.md); the new migration still needs PostgreSQL VM integration verification.

Drafts can be **archived and restored with reasons**, preserving history and saved packets. Active drafts are shown by default; archived drafts remain accessible through the draft list scope selector. See [draft archiving](docs/DRAFT_ARCHIVING.md) for behavior, migration and verification limits.

The deal’s History tab links to **complete saved history**, including older versions beyond the recent activity list. See [history scope and verification](docs/DEAL_HISTORY.md).

Saved demo packets also support a private **ZIP export** with original HTML, captured JSON and a hash manifest. It exports one packet, excluding uploads and complete deal history; it is not a full backup. See [packet export](docs/DEMO_PACKET_EXPORT.md).

**Deal follow-ups** add internal reminders with owners, optional due dates, completion/reopening and history. Your open assignments appear on Home. No customer communications are sent. See [follow-up behavior and verification](docs/DEAL_FOLLOWUPS.md).

## PostgreSQL integration and synthetic ledger

An optional owner-only local PostgreSQL setup is documented in [POSTGRES_INTEGRATION.md](docs/POSTGRES_INTEGRATION.md), with `dev/postgres.sh` for existing initialized environments. All current migrations and the 237-test suite have been verified on a fresh PostgreSQL 17.11 database; this is separate from the original offline VM and does not validate an upgrade of that VM's data.

`/ledger-demo/` offers an explicitly synthetic accounting rehearsal: opening provenance, unapplied manual receipts, linked full corrections and reconciliation. Every posting is previewed first. No loan, real payment, allocation, interest or bank settlement is created. See [ledger scope, source review and remaining gates](docs/LEDGER_FOUNDATION.md).


Draft financing proposals support explicit Precomputed or Simple interest selection. Separate saved synthetic schedule illustrations support monthly and other cadences without changing ledger balances. See [schedule methods and production boundaries](docs/SCHEDULE_METHODS.md).


[BHPH account workspace](docs/BHPH_ACCOUNT_WORKSPACE.md) brings linked draft context, customer/vehicle identification, schedule illustrations and synthetic payment receipts together. Development only; recorded demo funds remain unapplied.

Monthly precomputed accounts also support an explicit [demo servicing baseline](docs/DEMO_SERVICING.md): simulate installment coverage, partial/extra payments, reversals, and labeled red/green due status against a retained schedule. Receipts remain unapplied in the ledger. No live servicing, principal/earned-interest allocation, payoff or legal readiness is implied.

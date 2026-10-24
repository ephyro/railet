# Railet

**A clearer workspace for independent dealerships.**

Railet is an open-source dealership management system by [Ephyro](https://github.com/ephyro), started by a Florida independent dealer who also runs a buy-here-pay-here operation. The goal is practical: enter information once, find what you need, and complete dealership work without fighting the software.

We're building in public and welcome developers, dealership staff, and IT operators who want to help shape it.

> **Early development — synthetic data only.** This is a working prototype, not a production DMS. Do not enter actual customer information or use it for live transactions. Contracts, lending calculations, servicing, live payments, electronic signing, MFA, and production acceptance remain outstanding. Public source availability does not establish regulatory compliance.

## What works today

- Inventory with stock/VIN search, title brands, odometer details, costs, private photos, and duplicate VIN review.
- Shared customer records reused across buyers, co-buyers, and draft deals.
- A deal workspace with itemized draft amounts, trades, optional financing proposals, saved history, and a read-only review.
- Private supporting PDFs with authorized downloads, archive/restore, and upload retry protection in development.
- Reusable filters, sorting, pagination, and personal saved views.
- Dealership scoping, owner/staff/viewer roles, revision checks, and transactional change records.

Draft amounts are estimates. Manually entered taxes and fees are not legal calculations. Saving a draft does not sell or reserve a vehicle, create a contract or loan, or record money received. Supporting PDFs are stored as uploaded; they are not scanned or verified. Audit records are not protected from privileged direct database modification.

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

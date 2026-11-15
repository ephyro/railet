# Development

Use synthetic data only. Read [AGENTS.md](../AGENTS.md) and [the plan](RAILET_PLAN.md) before architecture, financial, document, security, or licensing changes.

## Docker and PostgreSQL

Follow the [README](../README.md) quick start. The development server binds to host loopback; it is not a production web server. Source mounts are read-only in the container. Python edits reload automatically; refresh for templates/CSS. Dependency or Dockerfile changes require `docker compose up --build -d`. Apply migrations explicitly.

```sh
docker compose logs -f web
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py test
```

If Docker requires elevation, use your host's configured `doas` or `sudo`. Database and uploads are separate volumes: preserve both when backing up. Container recreation has been checked; that is not evidence of successful backup restoration.

## Local Python

Python 3.12–3.14 is recommended. PostgreSQL is authoritative for transaction/concurrency checks. SQLite is an explicit local convenience:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export RAILET_DEBUG=1
export RAILET_SQLITE=1
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo
.venv/bin/python manage.py test
.venv/bin/python manage.py runserver
```

For PostgreSQL, omit `RAILET_SQLITE` and configure `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and `POSTGRES_PORT`. `RAILET_DEBUG=1` is an explicit development opt-in. Debug-off settings require a secret key and enforce HTTPS/cookie defaults; those defaults alone are not production hardening.

Generate migrations in a writable local checkout, then apply them in the container:

```sh
RAILET_DEBUG=1 RAILET_SQLITE=1 .venv/bin/python manage.py makemigrations inventory
docker compose exec web python manage.py migrate
```

Replace `inventory` with the changed app. The demo command refuses to change an existing username. For automation it accepts `--password-file /path/to/private-file`, requiring owner-only file permissions; never commit that file or put passwords in command arguments.

## Modules and checks

`core` owns dealerships, memberships, filters, personal views, vehicle audit events, and owner-only synthetic foundation/dealership export orchestration (`core/export.py`, `core/dealership_export.py`). `feedback` owns private local workflow reports and their preview/confirmation flow. `inventory`, `customers`, `deals`, `documents`, and `finance` own their respective records and expose explicit interfaces (Customer change history lives on `customers.CustomerEvent`). Draft deal events retain versioned snapshots. No microservices, task queue, frontend framework, or external CDN is needed for the current slice.

The pre-publication development-VM PostgreSQL run passed 153 tests on October 24, 2026, including authorization, isolation, rollback, retries, and concurrency cases. Firefox developer checks exercised selected workflows and responsive layouts. These are developer checks, not dealership staff validation, certification, or production acceptance. The GitHub Actions run reports its own results separately.

See [customers/deals](CUSTOMERS_AND_DEALS.md), [photos/filters](PHOTOS_AND_FILTERS.md), [financing proposals](DEAL_TYPES_AND_TERMS.md), [trades](TRADE_INS.md), [review](DEAL_REVIEW.md), [VIN review](DUPLICATE_VIN_REVIEW.md), [supporting PDFs](DEAL_FILES.md), [vehicle work and costs](VEHICLE_WORK_AND_COSTS.md), [completion rehearsal](DEMO_COMPLETION.md), and [ledger foundation](LEDGER_FOUNDATION.md) for implementation boundaries and remaining gates.

Historical PostgreSQL integration follow-up: a separate local PostgreSQL 17.11 instance passed all 237 tests at that October 2026 slice without skips (and 466 tests at the [November 2026 developer evaluation](EVALUATION_2026_11.md)); subsequent slices and migrations must be migrated and tested via `./dev/postgres.sh` on PostgreSQL as well as SQLite (see [REMAINING_WORK.md](REMAINING_WORK.md)). See [POSTGRES_INTEGRATION.md](POSTGRES_INTEGRATION.md) for the helper, migrated schema, browser/restore checks, [SYNTHETIC_RESTORE_EXERCISE.md](SYNTHETIC_RESTORE_EXERCISE.md) for the disposable `dev/restore_exercise.py` script, and the distinction from the original offline VM.

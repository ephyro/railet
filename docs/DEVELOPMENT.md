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

`core` owns dealerships, memberships, filters, personal views, and inventory/customer audit events. `inventory`, `customers`, `deals`, and `documents` own their respective records and expose explicit interfaces. Draft deal events retain versioned snapshots. No microservices, task queue, frontend framework, or external CDN is needed for the current slice.

The last full development-VM PostgreSQL run before initial publication passed 153 tests on October 24, 2026, including authorization, isolation, rollback, retries, and concurrency cases. Firefox developer checks exercised selected workflows and responsive layouts. These are developer checks, not dealership staff validation, certification, or production acceptance. The GitHub Actions run reports its own results separately.

See [customers/deals](CUSTOMERS_AND_DEALS.md), [photos/filters](PHOTOS_AND_FILTERS.md), [financing proposals](DEAL_TYPES_AND_TERMS.md), [trades](TRADE_INS.md), [review](DEAL_REVIEW.md), [VIN review](DUPLICATE_VIN_REVIEW.md), and [supporting PDFs](DEAL_FILES.md) for implementation boundaries and remaining gates.

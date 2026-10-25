#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# Optional owner-only PostgreSQL integration environment; never production hosting.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
pg_root="$project_dir/.local/pg-integration"
pg_bin="${RAILET_PG_BIN:-$pg_root/install/bin}"
pg_socket="$pg_root/socket"
pg_database="railet_integration"
pg_username="$(id -un)"
command_name="${1:-status}"
if [[ $# -gt 0 ]]; then shift; fi
[[ -x "$pg_bin/pg_ctl" ]] || { echo 'PostgreSQL tools are missing. Set RAILET_PG_BIN or see docs/POSTGRES_INTEGRATION.md.' >&2; exit 1; }
cd "$project_dir"
case "$command_name" in
  start)
    [[ -d "$pg_root/data" ]] || { echo 'Cluster is not initialized. Follow docs/POSTGRES_INTEGRATION.md; this helper never initializes or resets data.' >&2; exit 1; }
    mkdir -p "$pg_socket"
    chmod 700 "$pg_root" "$pg_socket"
    if "$pg_bin/pg_ctl" -D "$pg_root/data" status >/dev/null 2>&1; then
      echo 'Integration PostgreSQL is already running.'
    else
      # Socket path is quoted for pg_ctl's command string; reject quotes/newlines.
      [[ "$pg_socket" != *"'"* && "$pg_socket" != *$'\n'* ]] || { echo 'Unsupported socket path.' >&2; exit 1; }
      "$pg_bin/pg_ctl" -D "$pg_root/data" -l "$pg_root/server.log" -o "-k '$pg_socket' -p 55432 -c listen_addresses='' -c unix_socket_permissions=0700" start
    fi
    ;;
  stop) "$pg_bin/pg_ctl" -D "$pg_root/data" -m fast stop ;;
  status) "$pg_bin/pg_ctl" -D "$pg_root/data" status ;;
  check|migrate|test|showmigrations)
    exec env RAILET_DEBUG=1 RAILET_SQLITE=0 POSTGRES_HOST="$pg_socket" POSTGRES_PORT=55432 POSTGRES_USER="$pg_username" POSTGRES_DB="$pg_database" "$project_dir/.venv/bin/python" manage.py "$command_name" "$@"
    ;;
  *) echo 'Usage: dev/postgres.sh {start|stop|status|check|migrate|test|showmigrations} [manage.py arguments]' >&2; exit 1 ;;
esac

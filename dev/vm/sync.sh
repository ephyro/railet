#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$project_dir"
# Only project code and documentation are transferred; never secrets or VM disks.
rsync -az --relative --exclude='__pycache__' \
  -e "ssh -F /dev/null -p 2223 -i $project_dir/.local/vm-access/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes" \
  manage.py requirements.txt requirements-staging.txt Dockerfile compose.yaml compose.staging.yaml \
  core inventory customers deals documents railet templates static deploy dev docs README.md AGENTS.md LICENSE .dockerignore \
  dev@127.0.0.1:railet/

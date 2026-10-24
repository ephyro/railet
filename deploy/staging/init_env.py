# SPDX-License-Identifier: MPL-2.0
"""Generate local staging secrets without printing them or replacing existing files."""
import os
from pathlib import Path
import secrets

path = Path(__file__).resolve().parents[2] / ".env.staging"
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit(".env.staging already exists; left unchanged.")
with os.fdopen(fd, "w") as stream:
    stream.write(f"POSTGRES_PASSWORD={secrets.token_hex(32)}\n")
    stream.write(f"RAILET_SECRET_KEY={secrets.token_hex(48)}\n")
print("Created .env.staging with owner-only permissions. Secrets were not printed.")

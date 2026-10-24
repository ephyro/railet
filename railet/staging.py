# SPDX-License-Identifier: MPL-2.0
import os
from .settings import *  # noqa: F403

if DEBUG:  # noqa: F405
    raise RuntimeError("Staging must run with RAILET_DEBUG=0")
if os.getenv("RAILET_SQLITE") == "1":
    raise RuntimeError("Staging requires PostgreSQL")
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405
# Only the private Caddy network can reach Gunicorn. Caddy overwrites this header.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = ["https://localhost:8443"]
STORAGES = {
    "default": {"BACKEND": "core.storage.PrivateMediaStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
# Don't set long-lived HSTS on localhost shared with unrelated development apps.
SECURE_HSTS_SECONDS = 0

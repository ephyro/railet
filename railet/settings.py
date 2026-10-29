# SPDX-License-Identifier: MPL-2.0
import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv("RAILET_DEBUG", "0") == "1"
# Synthetic intake rehearsal only; production acquisition/title controls still require review.
TRADE_INTAKE_DEMO_ENABLED = DEBUG
# Supporting-file rehearsal remains synthetic-only until storage/security review.
DEAL_FILES_DEMO_ENABLED = DEBUG
DEMO_PACKETS_ENABLED = DEBUG
DEMO_LEDGER_ENABLED = DEBUG
DEMO_SERVICING_ENABLED = DEBUG
SECRET_KEY = os.environ.get("RAILET_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("Set RAILET_SECRET_KEY or explicitly enable local RAILET_DEBUG=1")
    SECRET_KEY = "local-development-only-not-for-production"
ALLOWED_HOSTS = os.getenv("RAILET_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "core", "inventory", "customers", "deals", "documents", "feedback", "finance"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF = "railet.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "railet.wsgi.application"
if os.getenv("RAILET_SQLITE") == "1":
    if not DEBUG:
        raise RuntimeError("SQLite is only supported for local development")
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "dev.sqlite3"}}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": os.getenv("POSTGRES_DB", "railet"), "USER": os.getenv("POSTGRES_USER", "railet"), "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""), "HOST": os.getenv("POSTGRES_HOST", "localhost"), "PORT": os.getenv("POSTGRES_PORT", "5432")}}
AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"}, {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"}, {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"}, {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"}]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/New_York"
USE_TZ = True
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path(os.getenv("RAILET_PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private-media")))
STORAGES = {"default": {"BACKEND": "core.storage.PrivateMediaStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "today"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Research-backed draft estimates only; live tax/contract production gates remain closed.
FL_TAX_ESTIMATES_ENABLED = DEBUG

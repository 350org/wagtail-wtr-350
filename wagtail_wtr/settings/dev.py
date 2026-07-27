import os

import dj_database_url

from .base import *  # noqa: F401, F403

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Use Postgres when DATABASE_URL is set (e.g. `divio app up` / docker-compose),
# otherwise fall back to the local SQLite database from base.py.
if os.environ.get("DATABASE_URL"):
    DATABASES = {"default": dj_database_url.config(conn_max_age=600)}  # noqa: F405

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-dev-key-not-for-production-use-change-me"

ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

WAGTAILADMIN_BASE_URL = "http://localhost:8000"

# Disable Usercentrics locally — the country injection relies on a Cloudflare
# Worker that isn't in front of the dev server, and we don't want the external
# CDN script loading during local development.
WTRX_USERCENTRICS_SETTINGS_ID = ""

# Disable 2FA enforcement locally so developers aren't forced into TOTP
# enrollment just to run the admin. Still fully enforced in production.
WAGTAIL_2FA_REQUIRED = False

try:
    from .local import *  # noqa: F401, F403
except ImportError:
    pass

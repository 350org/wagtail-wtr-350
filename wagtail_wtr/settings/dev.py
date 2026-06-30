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

try:
    from .local import *  # noqa: F401, F403
except ImportError:
    pass

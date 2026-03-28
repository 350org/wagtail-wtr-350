"""
Django settings for wagtail_wtr project.

Requires Python 3.13+, Django 5.2 LTS, Wagtail 7.0 LTS.
"""

import os

from django.utils.translation import gettext_lazy as _

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(PROJECT_DIR)

# Overridden by dev.py (a hardcoded insecure key) and production.py (os.environ["SECRET_KEY"]).
# base.py must never be used as DJANGO_SETTINGS_MODULE directly.
# If SECRET_KEY is not overridden, Django's --deploy check will warn,
# and production.py will crash with KeyError if SECRET_KEY env var is absent.
SECRET_KEY = "base-settings-placeholder-not-for-use"

DEBUG = False

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "wtrx",
    "wagtail_storages",
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.contrib.settings",
    "wagtail.contrib.frontend_cache",
    "wagtail.contrib.table_block",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail.locales",
    "wagtail",
    "wagtail_localize",
    "modelcluster",
    "taggit",
    "wagtailmedia",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

ROOT_URLCONF = "wagtail_wtr.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            os.path.join(BASE_DIR, "templates"),
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "wagtail.contrib.settings.context_processors.settings",
            ],
        },
    },
]

WSGI_APPLICATION = "wagtail_wtr.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
USE_I18N = True
WAGTAIL_I18N_ENABLED = True
LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_TZ = True

WAGTAIL_CONTENT_LANGUAGES = LANGUAGES = [
    ("en", _("English")),
    # Sites add languages as needed:
    # ('es', _('Spanish')),
    # ('fr', _('French')),
]

# Static files
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static_compiled"),
]

STATIC_ROOT = os.path.join(BASE_DIR, "static")
STATIC_URL = "/static/"

MEDIA_ROOT = os.path.join(BASE_DIR, "media")
MEDIA_URL = "/media/"

# Wagtail settings
WAGTAIL_SITE_NAME = "My Site"
# WAGTAILADMIN_BASE_URL is set in dev.py and production.py
WAGTAILIMAGES_IMAGE_MODEL = "wtrx.CustomImage"

WAGTAILSEARCH_BACKENDS = {
    "default": {
        "BACKEND": "wagtail.search.backends.database",
    }
}

WAGTAIL_ENABLE_UPDATE_CHECK = False

# wtrx platform settings
WTRX_DONATION_PLATFORM = "none"  # none, actblue
WTRX_SIGNUP_PLATFORM = "wagtail_forms"  # wagtail_forms, action_network, none

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

"""
Django settings for wagtail_wtr project.

Requires Python 3.13+, Django 5.2 LTS, Wagtail 7.1+ (moved off the 7.0 LTS
line to satisfy wagtail-ai's Wagtail>=7.1 requirement).
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
    "wagtail_ai",
    "wagtail_2fa",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
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
    "wagtail_wtr.middleware.ScopedVerifyUserMiddleware",
    "allauth.account.middleware.AccountMiddleware",
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
                "wtrx.context_processors.usercentrics",
                "wtrx.context_processors.google_sso",
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

# Wagtail 2FA — required for all staff/superusers accessing the admin.
# Disabled in dev.py so local development doesn't require TOTP enrollment.
WAGTAIL_2FA_REQUIRED = True

# Wagtail AI — content-assist tools (title/description suggestions, rich text
# actions, etc.) backed by Claude via the `llm` library's Anthropic plugin
# (llm-anthropic). Requires ANTHROPIC_API_KEY to be set in the environment;
# the anthropic SDK reads it directly, so no key is stored here or in the DB.
# TOKEN_LIMIT is required explicitly: wagtail-ai only ships default token
# limits for a handful of OpenAI models (see wagtail_ai.tokens), so Claude
# models raise ImproperlyConfigured without one. This limits how much text
# gets sent per completion/correction chunk, well under Claude's 200k context.
WAGTAIL_AI = {
    "BACKENDS": {
        "default": {
            "CLASS": "wagtail_ai.ai.llm.LLMBackend",
            "CONFIG": {
                "MODEL_ID": "anthropic/claude-sonnet-4-5",
                "TOKEN_LIMIT": 100000,
            },
        },
    },
}

# Google SSO (django-allauth) — "Sign in with Google" alongside the regular
# username/password form on the Wagtail admin login page (see the
# templates/wagtailadmin/login.html override). Client credentials come from
# GOOGLE_OAUTH_CLIENT_ID/SECRET env vars (no SocialApp DB row needed).
# WTRX_GOOGLE_SSO_DOMAIN restricts sign-in to a single Google Workspace
# domain, enforced server-side in wtrx.allauth_adapter — leaving it unset
# disables the domain check (any Google account could sign in), so it should
# always be set outside of local dev.
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ACCOUNT_ADAPTER = "wtrx.allauth_adapter.NoSignupAccountAdapter"
SOCIALACCOUNT_ADAPTER = "wtrx.allauth_adapter.DomainRestrictedSocialAccountAdapter"

# New Google-authenticated users are created with is_staff=False — an
# existing superuser must still grant Wagtail admin access via the Users
# section before they can do anything.
SOCIALACCOUNT_AUTO_SIGNUP = True
ACCOUNT_EMAIL_VERIFICATION = "none"  # Google has already verified the email
# Skip allauth's unstyled intermediate "Continue" confirmation page — the
# login template's button already is the deliberate click that starts SSO.
SOCIALACCOUNT_LOGIN_ON_GET = True

WTRX_GOOGLE_SSO_DOMAIN = os.environ.get("WTRX_GOOGLE_SSO_DOMAIN", "")

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": (
            {"hd": WTRX_GOOGLE_SSO_DOMAIN} if WTRX_GOOGLE_SSO_DOMAIN else {}
        ),
        "OAUTH_PKCE_ENABLED": True,
        "APP": {
            "client_id": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
            "secret": os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "key": "",
        },
    }
}

# wtrx platform settings
WTRX_DONATION_PLATFORM = "none"  # none, actblue
WTRX_SIGNUP_PLATFORM = "wagtail_forms"  # wagtail_forms, action_network, none

# Usercentrics consent management:
# The consent snippet renders only when WTRX_USERCENTRICS_SETTINGS_ID is non-empty;
# dev.py blanks it so the external CDN script does not load in local development.
# Requires a Cloudflare Worker to inject the visitor country.
WTRX_USERCENTRICS_SETTINGS_ID = os.environ.get(
    "WTRX_USERCENTRICS_SETTINGS_ID", "AcMHYQUX2Y80Au"
)
WTRX_USERCENTRICS_VERSION = os.environ.get("WTRX_USERCENTRICS_VERSION", "1.1.4")
# Visitor country used to decide whether to show the consent banner. Defaults to
# an EU/GDPR country so the banner shows for everyone — correct when the site is
# NOT behind Cloudflare (e.g. plain Divio). Set to "" to instead emit the
# {{COUNTRY}} placeholder for the Cloudflare Worker to fill per-visitor.
WTRX_USERCENTRICS_COUNTRY = os.environ.get("WTRX_USERCENTRICS_COUNTRY", "DE")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

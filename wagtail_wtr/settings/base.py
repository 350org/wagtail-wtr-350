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
    # Stashes the current request for wtrx.blocks — BodyStreamBlock/
    # SectionContentBlock need it to filter the "Add block" picker by
    # IntegrationSettings, and Wagtail's Telepath adapter that builds that
    # picker is called with no request argument (see wtrx/request_context.py).
    "wtrx.request_context.CurrentRequestMiddleware",
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
WAGTAIL_SITE_NAME = "350.org"
# WAGTAILADMIN_BASE_URL is set in dev.py and production.py
WAGTAILIMAGES_IMAGE_MODEL = "wtrx.CustomImage"
WAGTAILIMAGES_EXTENSIONS = ["avif", "gif", "jpg", "jpeg", "png", "webp", "svg"]

WAGTAILSEARCH_BACKENDS = {
    "default": {
        "BACKEND": "wagtail.search.backends.database",
    }
}

WAGTAIL_ENABLE_UPDATE_CHECK = False

# Wagtail 2FA — required for all staff/superusers accessing the admin.
# Disabled in dev.py so local development doesn't require TOTP enrollment.
WAGTAIL_2FA_REQUIRED = True
# Shown as the issuer name next to each account's label in an authenticator
# app during TOTP enrolment (django_otp reads this directly — see
# OTP_TOTP_ISSUER in its docs). wagtail_2fa would otherwise fall back to
# WAGTAIL_SITE_NAME above, which is still Wagtail's own unconfigured "My
# Site" placeholder, not a useful identifier. The per-account label itself
# is the user's email — see NoSignupAccountAdapter.populate_username in
# wtrx/allauth_adapter.py.
OTP_TOTP_ISSUER = "350 Wagtail CMS"

# Wagtail AI — content-assist tools (title/description suggestions, rich text
# actions, alt text, etc.) backed by Claude. Requires ANTHROPIC_API_KEY to be
# set in the environment; the Anthropic SDK reads it directly, so no key is
# stored here or in the DB.
#
# Two separate config blocks are both required — wagtail-ai routes different
# features through different subsystems, each with its own settings key:
# - BACKENDS: used by the rich-text Draftail "ai" feature (text_completion/
#   describe_image views — see wagtail_ai/views.py). TOKEN_LIMIT is required
#   explicitly here: wagtail-ai only ships default token limits for a
#   handful of OpenAI models (see wagtail_ai.tokens), so Claude models raise
#   ImproperlyConfigured without one.
# - PROVIDERS: used by the newer agents-based actions (AITitleFieldPanel,
#   AIDescriptionFieldPanel, ai_image_block()'s "generate alt text" — see
#   wagtail_ai/agents/basic_prompt.py). Without an explicit "default" entry
#   here, wagtail-ai falls back to a deprecated legacy path that hardcodes
#   the "openai" provider regardless of BACKENDS' MODEL_ID, raising
#   MissingApiKeyError since OPENAI_API_KEY isn't (and shouldn't be) set.
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
    "PROVIDERS": {
        "default": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-5",
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
# WTRX_GOOGLE_SSO_ONLY hides the username/password fields and submit button
# on the login page (see wtrx.context_processors.google_sso and the
# templates/wagtailadmin/login.html override) when Google SSO is configured.
# This is a UI-only change — password authentication itself still works if
# posted directly to the login form — so a superuser always has a fallback
# if Google SSO is ever misconfigured or Google has an outage.
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

# Without this pair, a user whose account a superuser pre-created in the
# Wagtail Users admin (matching email, no SocialAccount yet) cannot complete
# SSO at all: allauth sees the email is already taken by a local account and
# refuses auto-signup rather than logging into it, bouncing the user to the
# unstyled allauth "sign up" form, which then fails again on the same email
# collision — an unrecoverable loop that ends with the user trying to type a
# password into allauth's own login form for an account that (per
# NoSignupAccountAdapter/wtrx/forms.py) has none. EMAIL_AUTHENTICATION treats
# a Google-verified email match against an existing local account as a login
# to that account instead of a signup conflict — safe here because Google is
# the only configured provider and email verification is trustworthy.
# AUTO_CONNECT persists that match as a real SocialAccount so later logins
# take the fast lookup-by-provider-id path instead of re-matching by email
# every time.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

WTRX_GOOGLE_SSO_DOMAIN = os.environ.get("WTRX_GOOGLE_SSO_DOMAIN", "")
WTRX_GOOGLE_SSO_ONLY = os.environ.get("WTRX_GOOGLE_SSO_ONLY", "false").lower() in (
    "true",
    "1",
    "yes",
)

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

# wtrx integration secret overrides — take precedence over the DB-stored
# value in the corresponding integration's config (Settings > Integrations)
# so secrets aren't required to live in the database in production.
WTRX_ACTION_NETWORK_API_KEY = os.environ.get("WTRX_ACTION_NETWORK_API_KEY", "")
WTRX_ACTIONKIT_API_PASSWORD = os.environ.get("WTRX_ACTIONKIT_API_PASSWORD", "")

# Usercentrics consent management:
# The consent snippet renders only when WTRX_USERCENTRICS_SETTINGS_ID is non-empty;
# dev.py blanks it so the external CDN script does not load in local development.
# Visitor country is determined client-side via Cloudflare's built-in
# /cdn-cgi/trace edge endpoint (see usercentrics_head.html) — no Cloudflare
# Worker or Django involvement required.
WTRX_USERCENTRICS_SETTINGS_ID = os.environ.get(
    "WTRX_USERCENTRICS_SETTINGS_ID", "AelB3mtRNvAY5D"
)
WTRX_USERCENTRICS_VERSION = os.environ.get("WTRX_USERCENTRICS_VERSION", "1.1.4")
# Manual override for the visitor's country — bypasses the /cdn-cgi/trace fetch
# entirely and uses this literal value instead. Intended for local/QA testing
# of a specific country only; leave blank in production so every visitor's
# real, Cloudflare-edge-detected country is used instead of a fixed one.
WTRX_USERCENTRICS_COUNTRY = os.environ.get("WTRX_USERCENTRICS_COUNTRY", "")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

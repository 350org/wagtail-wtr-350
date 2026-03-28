import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403

DEBUG = False

SECRET_KEY = os.environ["SECRET_KEY"]  # noqa: F405

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()
]  # noqa: F405
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "ALLOWED_HOSTS env var is required in production. "
        "Set it to a comma-separated list of hostnames (e.g. mysite.onrender.com)."
    )

WAGTAILADMIN_BASE_URL = os.environ["WAGTAILADMIN_BASE_URL"]  # noqa: F405

DATABASES = {"default": dj_database_url.config(conn_max_age=600)}

# Whitenoise static file serving — SecurityMiddleware must be first, WhiteNoise second
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# ---------------------------------------------------------------------------
# AWS S3 media storage (optional — omit AWS_STORAGE_BUCKET_NAME to disable)
# When configured, user-uploaded media (images, documents) is stored in S3.
# Static files continue to be served by WhiteNoise from the container.
#
# WARNING: Without S3, media is stored on the local filesystem. Render's
# Docker containers have ephemeral disks — media will be lost on every deploy.
# Always configure S3 (or another persistent storage backend) for production
# deployments where editors upload images or documents.
# ---------------------------------------------------------------------------
_s3_bucket = os.environ.get("AWS_STORAGE_BUCKET_NAME")
if _s3_bucket:
    _s3_custom_domain = os.environ.get("AWS_S3_CUSTOM_DOMAIN")
    _aws_expiry = 60 * 60 * 24 * 7  # 7 days

    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": _s3_bucket,
            "region_name": os.environ.get("AWS_S3_REGION_NAME", "us-east-1"),
            "access_key": os.environ.get("AWS_ACCESS_KEY_ID"),
            "secret_key": os.environ.get("AWS_SECRET_ACCESS_KEY"),
            "custom_domain": _s3_custom_domain,
            "querystring_auth": False,  # public bucket; wagtail-storages handles signed URLs for private docs
            "file_overwrite": False,  # prevent overwriting existing files (Wagtail requirement)
            "object_parameters": {
                "CacheControl": f"max-age={_aws_expiry}, s-maxage={_aws_expiry}, must-revalidate",
            },
        },
    }

    if _s3_custom_domain:
        MEDIA_URL = f"https://{_s3_custom_domain}/"  # noqa: F405
    else:
        MEDIA_URL = f"https://{_s3_bucket}.s3.amazonaws.com/"  # noqa: F405

# ---------------------------------------------------------------------------
# Email / SMTP (optional — omit EMAIL_HOST to fall back to console backend)
# Compatible with any SMTP provider: Mailgun, AWS SES, Postmark, etc.
# When EMAIL_HOST is unset, emails are printed to stdout (container logs).
# ---------------------------------------------------------------------------
_email_host = os.environ.get("EMAIL_HOST")
if _email_host:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = _email_host
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() in (
        "true",
        "1",
        "yes",
    )
    EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "false").lower() in (
        "true",
        "1",
        "yes",
    )
    if EMAIL_USE_TLS and EMAIL_USE_SSL:
        raise ImproperlyConfigured(
            "EMAIL_USE_TLS and EMAIL_USE_SSL are mutually exclusive. "
            "Use EMAIL_USE_TLS=true for STARTTLS (port 587) or "
            "EMAIL_USE_SSL=true for implicit SSL (port 465) — not both."
        )
    DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "webmaster@localhost")
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# Cloudflare cache invalidation (optional — omit env vars to disable)
# ---------------------------------------------------------------------------
_cf_token = os.environ.get("CLOUDFLARE_BEARER_TOKEN")
_cf_zone = os.environ.get("CLOUDFLARE_ZONE_ID")
if _cf_token and _cf_zone:
    WAGTAILFRONTENDCACHE = {
        "cloudflare": {
            "BACKEND": "wagtail.contrib.frontend_cache.backends.CloudflareBackend",
            "BEARER_TOKEN": _cf_token,
            "ZONEID": _cf_zone,
        },
    }

try:
    from .local import *  # noqa: F401, F403
except ImportError:
    pass

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

# Docker / PaaS probes often use Host: 127.0.0.1:<port> or localhost. Without these,
# Django returns 400 and reverse proxies mark the container unhealthy.
for _loopback in ("127.0.0.1", "localhost"):
    if _loopback not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_loopback)

WAGTAILADMIN_BASE_URL = os.environ["WAGTAILADMIN_BASE_URL"]  # noqa: F405

DATABASES = {"default": dj_database_url.config(conn_max_age=600)}

_s3_bucket = os.environ.get("AWS_STORAGE_BUCKET_NAME")

# AssumeTlsFromEdgeMiddleware runs before SecurityMiddleware so SECURE_PROXY_SSL_HEADER
# sees https when TRUST_EDGE_TLS is set. WhiteNoise must follow SecurityMiddleware.
_MIDDLEWARE_SECURITY_PREFIX = [
    "wagtail_wtr.middleware.AssumeTlsFromEdgeMiddleware",
    "django.middleware.security.SecurityMiddleware",
]
_MIDDLEWARE_TAIL = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

if _s3_bucket:
    MIDDLEWARE = _MIDDLEWARE_SECURITY_PREFIX + _MIDDLEWARE_TAIL
else:
    MIDDLEWARE = _MIDDLEWARE_SECURITY_PREFIX + [
        "whitenoise.middleware.WhiteNoiseMiddleware",
        *_MIDDLEWARE_TAIL,
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
# Exempt the health check from SSL redirect so Render's HTTP scanner can reach it.
SECURE_REDIRECT_EXEMPT = [r"^_health/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# ---------------------------------------------------------------------------
# AWS S3 storage (optional — omit AWS_STORAGE_BUCKET_NAME to disable)
# When configured, both user-uploaded media AND collected static files are
# stored in S3 under separate prefixes (media/ and static/).
#
# Bucket layout:
#   {bucket}/static/  — collected static assets (CSS, JS, fonts)
#   {bucket}/media/   — user-uploaded content (images, documents)
#
# When S3 is configured, collectstatic runs in Render's preDeployCommand
# (render.yaml) before the container starts so gunicorn binds immediately
# and the health check responds without delay.
# When S3 is not configured (WhiteNoise path), collectstatic runs in
# start.sh instead so the manifest lands in the correct container filesystem.
#
# WARNING: Without S3, media is stored on the local filesystem. Render's
# Docker containers have ephemeral disks — media will be lost on every deploy.
# Always configure S3 (or another persistent storage backend) for production
# deployments where editors upload images or documents.
# ---------------------------------------------------------------------------
if _s3_bucket:
    _s3_custom_domain = os.environ.get("AWS_S3_CUSTOM_DOMAIN")
    _aws_expiry = 60 * 60 * 24 * 7  # 7 days

    # Shared S3 options for both storage backends.
    # NOTE: django-storages 1.14+ reads all S3 config from the OPTIONS dict only.
    # Only pass explicit credentials when set — omitting them lets boto3 use its
    # full credential chain (env vars, ~/.aws/credentials, IAM instance role).
    _s3_region = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")
    _s3_opts_base = {
        "bucket_name": _s3_bucket,
        "region_name": _s3_region,
        "custom_domain": _s3_custom_domain,
        "querystring_auth": False,  # public read; all objects in this bucket are publicly accessible via direct URL
    }
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        _secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
        if not _secret:
            raise ImproperlyConfigured(
                "AWS_ACCESS_KEY_ID is set but AWS_SECRET_ACCESS_KEY is missing. "
                "Either set both, or omit AWS_ACCESS_KEY_ID to use IAM role credentials."
            )
        _s3_opts_base["access_key"] = os.environ["AWS_ACCESS_KEY_ID"]
        _s3_opts_base["secret_key"] = _secret

    # Media storage — user uploads, file_overwrite=False required by Wagtail.
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **_s3_opts_base,
            "location": "media",
            "file_overwrite": False,
            "object_parameters": {
                "CacheControl": f"max-age={_aws_expiry}, s-maxage={_aws_expiry}, must-revalidate",
            },
        },
    }

    # Static files storage — S3ManifestStaticStorage layers ManifestFilesMixin
    # on top of S3Storage, rewriting asset URLs with content-hash suffixes
    # (e.g. main.abc123de.css) for safe far-future Cache-Control headers.
    # file_overwrite=True is correct here: collectstatic regenerates files
    # deterministically on each deploy and filenames change with content.
    STORAGES["staticfiles"] = {
        "BACKEND": "wtrx.storage_backends.S3ManifestStaticStorage",
        "OPTIONS": {
            **_s3_opts_base,
            "location": "static",
            "file_overwrite": True,
            "object_parameters": {
                "CacheControl": f"max-age={_aws_expiry}, s-maxage={_aws_expiry}, must-revalidate",
            },
        },
    }

    _s3_base_url = (
        f"https://{_s3_custom_domain}"
        if _s3_custom_domain
        else f"https://{_s3_bucket}.s3.{_s3_region}.amazonaws.com"
    )
    MEDIA_URL = f"{_s3_base_url}/media/"  # noqa: F405
    STATIC_URL = f"{_s3_base_url}/static/"  # noqa: F405

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

# local.py overrides are applied last — any STORAGES, MIDDLEWARE, or URL
# settings defined there will supersede the S3 configuration above.
try:
    from .local import *  # noqa: F401, F403
except ImportError:
    pass

import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403

# Divio's "Object Storage" service injects these DEFAULT_STORAGE_* env vars
# directly at runtime (bucket, endpoint, credentials, region) — no DSN
# parsing needed. Map them onto the discrete AWS_* env vars the S3 config
# below already reads. Only sets vars that aren't already set (see
# setdefault() below), so an explicit AWS_* var always wins, and Render
# deployments (which set discrete AWS_* vars against a real AWS bucket, no
# DEFAULT_STORAGE_* vars involved) are unaffected.
#
# Deliberately does NOT map DEFAULT_STORAGE_CUSTOM_DOMAIN onto
# AWS_S3_CUSTOM_DOMAIN — django-storages concatenates custom_domain directly
# with "/{key}" (see its url() method), so a virtual-hosted-style domain
# (bucket baked into the domain, e.g. "<bucket>.divio-media.com") breaks
# HTTPS for any dotted domain (SSL cert mismatch). Leaving AWS_S3_CUSTOM_DOMAIN
# unset lets django-storages build the URL itself via boto3 from bucket +
# endpoint_url + addressing_style="path" (see the "path" default below),
# which is correct regardless of the domain's shape.
_DIVIO_STORAGE_ENV_MAP = {
    "AWS_STORAGE_BUCKET_NAME": "DEFAULT_STORAGE_BUCKET",
    "AWS_ACCESS_KEY_ID": "DEFAULT_STORAGE_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY": "DEFAULT_STORAGE_SECRET_ACCESS_KEY",
    "AWS_S3_ENDPOINT_URL": "DEFAULT_STORAGE_ENDPOINT_URL",
    "AWS_S3_REGION_NAME": "DEFAULT_STORAGE_REGION",
}
if os.environ.get("DEFAULT_STORAGE_BUCKET"):
    for _aws_key, _divio_key in _DIVIO_STORAGE_ENV_MAP.items():
        _divio_value = os.environ.get(_divio_key)
        if _divio_value:
            os.environ.setdefault(_aws_key, _divio_value)

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

# ssl_require=True: some managed Postgres instances (e.g. certain RDS parameter
# groups) enforce SSL and refuse plaintext connections outright. Connecting
# over SSL works whether or not the server actually requires it, so forcing it
# here is safe regardless — and avoids depending on knowing (or being able to
# check) the target instance's specific enforcement setting. (The actual fix
# for the $HOME/.postgresql/postgresql.crt permission error this surfaced
# lives in bin/start.sh, not here — see the comment there.)
DATABASES = {"default": dj_database_url.config(conn_max_age=600, ssl_require=True)}

_s3_bucket = os.environ.get("AWS_STORAGE_BUCKET_NAME")

# AssumeTlsFromEdgeMiddleware runs before SecurityMiddleware so SECURE_PROXY_SSL_HEADER
# sees https when TRUST_EDGE_TLS is set. WhiteNoise must follow SecurityMiddleware.
#
# Builds on base.py's MIDDLEWARE (imported via `from .base import *` above)
# rather than re-declaring the whole list here — a hand-duplicated copy
# silently drifted out of sync in the past (missing a middleware entry added
# to base.py caused a 500 on every admin page in production; see git log).
assert MIDDLEWARE[0] == "django.middleware.security.SecurityMiddleware"  # noqa: F405
MIDDLEWARE = [  # noqa: F405
    "wagtail_wtr.middleware.AssumeTlsFromEdgeMiddleware",
    MIDDLEWARE[0],  # noqa: F405
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[1:],  # noqa: F405
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
# AWS S3 storage for MEDIA ONLY (optional — omit AWS_STORAGE_BUCKET_NAME to disable)
# When configured, user-uploaded media (images, documents) is stored in S3 under
# the media/ prefix. Static files (CSS, JS, fonts) are NOT put on S3 — they are
# always served by WhiteNoise from the container's STATIC_ROOT, with collectstatic
# run at container startup by bin/start.sh in every environment. This decoupling
# keeps static serving reliable on platforms without a pre-deploy hook (e.g. Divio),
# while still giving media persistent, shared storage.
#
# WARNING: Without S3, media is stored on the local filesystem, which is ephemeral
# on Divio/Render — uploads are lost on every deploy. Configure S3 for any
# deployment where editors upload images or documents.
# ---------------------------------------------------------------------------
if _s3_bucket:
    _s3_custom_domain = os.environ.get("AWS_S3_CUSTOM_DOMAIN")
    _aws_expiry = 60 * 60 * 24 * 7  # 7 days

    # Shared S3 options for both storage backends.
    # NOTE: django-storages 1.14+ reads all S3 config from the OPTIONS dict only.
    # Only pass explicit credentials when set — omitting them lets boto3 use its
    # full credential chain (env vars, ~/.aws/credentials, IAM instance role).
    _s3_region = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")
    _s3_endpoint_url = os.environ.get("AWS_S3_ENDPOINT_URL")
    _s3_opts_base = {
        "bucket_name": _s3_bucket,
        "region_name": _s3_region,
        "custom_domain": _s3_custom_domain,
        "endpoint_url": _s3_endpoint_url,  # non-AWS S3-compatible providers (e.g. Divio Object Storage)
        # Public read is achieved differently depending on how the bucket was
        # provisioned:
        #
        # - A manually-provisioned AWS bucket (bin/provision.sh) blocks
        #   public ACLs and grants public read via an explicit bucket policy
        #   instead (its "Apply bucket policy" step) — no per-object ACL
        #   needed, so AWS_S3_DEFAULT_ACL should stay unset there (sending an
        #   ACL header to a bucket that blocks public ACLs is a hard error).
        # - Divio's "Object Storage" service does the opposite: its
        #   documentation (docs.divio.com/how-to/interact-storage/) says
        #   objects are private by default and must be given the
        #   'public-read' ACL individually, and confirms its credentials
        #   don't grant s3:PutBucketPolicy/PutPublicAccessBlock (verified
        #   directly — that call returns AccessDenied). Set
        #   AWS_S3_DEFAULT_ACL=public-read there; django-storages then sends
        #   an ACL header on every upload automatically.
        "default_acl": os.environ.get("AWS_S3_DEFAULT_ACL") or None,
        # Alternative to the ACL approach above, for a bucket that supports
        # neither a public bucket policy nor public ACLs: presigned URLs need
        # only s3:GetObject on our own credentials. Off by default since
        # every provider this project currently targets supports one of the
        # two options above.
        "querystring_auth": os.environ.get("AWS_QUERYSTRING_AUTH", "false").lower() in ("true", "1", "yes"),
        # Only takes effect when querystring_auth is True. Matches the
        # CacheControl max-age below so a signed URL stays valid at least as
        # long as a client/CDN might cache the page embedding it — a signed
        # URL that outlives its own page's cache window would 403 on reuse.
        "querystring_expire": _aws_expiry,
        # "path" (not virtual-hosted, boto3's default) works for every bucket
        # name, including ones containing a dot (e.g. "example.com") — a
        # dotted bucket name breaks HTTPS virtual-hosted-style addressing,
        # since it produces a hostname like "example.com.s3.amazonaws.com"
        # that AWS's own wildcard cert (*.s3.amazonaws.com) doesn't cover,
        # causing an SSL validation error on every request.
        "addressing_style": os.environ.get("AWS_S3_ADDRESSING_STYLE", "path"),
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

    # NOTE: static files are intentionally NOT placed on S3. STORAGES["staticfiles"]
    # keeps its WhiteNoise default (set above), and STATIC_URL keeps its local
    # default from base.py. Only media (STORAGES["default"]) uses S3.
    #
    # settings.MEDIA_URL is NOT set here (base.py's "/media/" default is left
    # as-is) — it's vestigial for S3-backed media: urls.py only ever consumes
    # it inside `if settings.DEBUG`, which production never is, and Wagtail's
    # own image rendering calls the storage instance's .url() directly
    # (django-storages' S3Storage.url(), which — since AWS_S3_CUSTOM_DOMAIN is
    # unset above — builds the URL itself via boto3, correctly respecting
    # addressing_style for any bucket name). A hand-built MEDIA_URL here would
    # just be a second, easy-to-drift copy of that same logic — see git log
    # for a prior version of this file that got the dotted-bucket-name case
    # wrong by doing exactly that.

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
# Logging — with DEBUG=False, Django's own default LOGGING config only prints
# exceptions to console when DEBUG=True; otherwise it tries to email ADMINS
# (unset here) and the traceback goes nowhere. Every 500 was previously
# invisible in container logs because of this. Route django (request errors,
# security warnings, etc.) and our own app loggers (logging.getLogger(__name__)
# in views.py/models.py) to stderr, which gunicorn's --error-logfile - and
# Divio both already capture.
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

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

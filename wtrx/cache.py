"""
Provider-agnostic CDN cache invalidation for wtrx.

Usage
-----
- ``purge_all()``  — purge the entire site cache. Called when any site settings
  model is saved (header/footer changes affect every page).
- ``purge_page_with_related(page)`` — purge a single page and, if its parent is
  an IndexPage, purge the parent listing too. Called on page publish, unpublish,
  and slug change.

Adding a new CDN provider
--------------------------
1. Write a handler: ``def _purge_all_myprovider(backend_name, config): ...``
2. Register it in ``PURGE_ALL_HANDLERS`` keyed by the backend's dotted class path.

When ``WAGTAILFRONTENDCACHE`` is not configured (e.g. dev, or CF env vars absent)
all functions are silent no-ops. No exceptions are raised.
"""

import logging

import requests
from django.conf import settings
from wagtail.contrib.frontend_cache.utils import PurgeBatch

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cloudflare purge-all handler
# ---------------------------------------------------------------------------

_CF_API_URL = "https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache"


def _purge_all_cloudflare(backend_name, config):
    """Call the Cloudflare API to purge the entire zone cache.

    Supports both Bearer-token auth (preferred) and legacy Email+API-key auth.
    """
    zone_id = config.get("ZONEID") or config.get("ZONE_ID")
    if not zone_id:
        logger.warning(
            "wtrx cache: Cloudflare backend '%s' has no ZONEID — skipping purge_all.",
            backend_name,
        )
        return

    cf_bearer_token = config.get("BEARER_TOKEN")
    cf_email = config.get("EMAIL")
    cf_api_key = config.get("API_KEY")

    if cf_bearer_token:
        headers = {
            "Authorization": f"Bearer {cf_bearer_token}",
            "Content-Type": "application/json",
        }
    elif cf_email and cf_api_key:
        headers = {
            "X-Auth-Email": cf_email,
            "X-Auth-Key": cf_api_key,
            "Content-Type": "application/json",
        }
    else:
        logger.warning(
            "wtrx cache: Cloudflare backend '%s' has no BEARER_TOKEN or EMAIL+API_KEY — skipping purge_all.",
            backend_name,
        )
        return

    url = _CF_API_URL.format(zone_id=zone_id)
    try:
        response = requests.post(
            url, headers=headers, json={"purge_everything": True}, timeout=10
        )
        if response.ok:
            logger.info(
                "wtrx cache: Cloudflare purge_all succeeded for backend '%s'.",
                backend_name,
            )
        else:
            logger.error(
                "wtrx cache: Cloudflare purge_all failed for backend '%s': %s %s",
                backend_name,
                response.status_code,
                response.text[:500],
            )
    except requests.RequestException as exc:
        logger.error(
            "wtrx cache: Cloudflare purge_all request error for backend '%s': %s",
            backend_name,
            exc,
        )


# ---------------------------------------------------------------------------
# Fallback purge-all handler (purges all live page URLs via PurgeBatch)
# ---------------------------------------------------------------------------


def _purge_all_fallback(backend_name, config):
    """Fallback: purge all live page URLs one by one via PurgeBatch.

    Used for backends that don't support a single-call purge-everything API
    (e.g. a custom backend). Slower but broadly compatible.

    WARNING: On large sites this triggers N+1 queries (one per concrete page
    subtype) and may be very slow. Register a ``PURGE_ALL_HANDLERS`` entry for
    your CDN backend to use a faster purge-everything API instead.
    """
    from wagtail.models import (
        Page,
    )  # local import to avoid circular deps at module level

    logger.warning(
        "wtrx cache: using slow fallback purge_all for backend '%s'. "
        "Register a PURGE_ALL_HANDLERS entry for this backend to use "
        "a faster purge-everything API.",
        backend_name,
    )

    batch = PurgeBatch()
    for page in Page.objects.live().specific().iterator():
        try:
            url = page.get_full_url()
        except Exception as exc:
            logger.debug(
                "wtrx cache: could not resolve full_url for page pk=%s — skipping. %s",
                page.pk,
                exc,
            )
            continue
        if url:
            batch.add_url(url)

    url_count = len(batch.urls)
    if url_count:
        batch.purge()
        logger.info(
            "wtrx cache: fallback purge_all sent %d URLs for backend '%s'.",
            url_count,
            backend_name,
        )
    else:
        logger.debug(
            "wtrx cache: fallback purge_all found no live pages for backend '%s' — nothing to purge.",
            backend_name,
        )


# ---------------------------------------------------------------------------
# Registry: maps backend class path → purge-all handler
# ---------------------------------------------------------------------------

PURGE_ALL_HANDLERS = {
    "wagtail.contrib.frontend_cache.backends.CloudflareBackend": _purge_all_cloudflare,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def purge_all():
    """Purge the entire site cache across all configured CDN backends.

    Silent no-op when ``WAGTAILFRONTENDCACHE`` is not configured.
    """
    cache_config = getattr(settings, "WAGTAILFRONTENDCACHE", None)
    if not cache_config:
        return

    for backend_name, config in cache_config.items():
        backend_class = config.get("BACKEND", "")
        handler = PURGE_ALL_HANDLERS.get(backend_class, _purge_all_fallback)
        try:
            handler(backend_name, config)
        except Exception:
            logger.exception(
                "wtrx cache: unexpected error in purge_all handler for backend '%s'.",
                backend_name,
            )


def purge_page_with_related(page, extra_urls=None):
    """Purge a page and, if its parent is an IndexPage, purge the parent too.

    This keeps index/listing pages fresh whenever a child is published,
    unpublished, or has its slug changed.

    ``extra_urls`` is an optional iterable of additional URLs to include in the
    same purge batch (e.g. the pre-slug-change URL when a page slug is renamed).

    Silent no-op when ``WAGTAILFRONTENDCACHE`` is not configured.
    """
    cache_config = getattr(settings, "WAGTAILFRONTENDCACHE", None)
    if not cache_config:
        return

    from wtrx.models import IndexPage  # local import to avoid circular deps

    batch = PurgeBatch()

    try:
        page_url = page.get_full_url()
    except Exception as exc:
        logger.debug(
            "wtrx cache: could not resolve full_url for page pk=%s — skipping page purge. %s",
            getattr(page, "pk", "unknown"),
            exc,
        )
        page_url = None
    if page_url:
        batch.add_url(page_url)

    try:
        parent = page.get_parent().specific
        if isinstance(parent, IndexPage):
            parent_url = parent.get_full_url()
            if parent_url:
                batch.add_url(parent_url)
    except Exception as exc:
        logger.debug(
            "wtrx cache: could not resolve parent for page pk=%s — skipping parent purge. %s",
            getattr(page, "pk", "unknown"),
            exc,
        )

    if extra_urls:
        for url in extra_urls:
            if url:
                batch.add_url(url)

    if batch.urls:
        batch.purge()

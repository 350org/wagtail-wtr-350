"""
Django signal handlers for wtrx cache invalidation.

Registered in WtrxConfig.ready() (wtrx/apps.py).

- ``on_settings_saved`` — connected to ``post_save`` for every
  ``BaseSiteSetting`` model in wtrx. Any settings save triggers a full-site
  purge because header/footer content appears on every page.
- ``on_page_published`` — connected to Wagtail's ``page_published`` signal.
  Purges the published page and its parent IndexPage (if applicable) to keep
  listing pages fresh.
- ``on_page_unpublished`` — connected to Wagtail's ``page_unpublished`` signal.
  Purges the now-unpublished page and its parent IndexPage so stale entries
  are removed from listing pages.
- ``on_page_slug_changed`` — connected to Wagtail's ``page_slug_changed``
  signal. Purges both the old URL (via the page's cached pre-save URL) and the
  new URL so redirects and listing pages reflect the updated slug immediately.

Every purge is deferred with ``transaction.on_commit()``: these signals fire
inside the save's transaction, and purging before the commit lets a request
arriving in between re-cache the old content at the CDN.
"""

import logging

from django.db import transaction
from wagtail.signals import page_published, page_slug_changed, page_unpublished

from wtrx.cache import purge_all, purge_page_with_related

logger = logging.getLogger(__name__)


def on_settings_saved(sender, instance, **kwargs):
    """Trigger a full-site cache purge whenever any site settings model is saved."""
    logger.debug(
        "wtrx signals: settings saved (%s pk=%s) — triggering purge_all.",
        sender.__name__,
        instance.pk,
    )
    transaction.on_commit(purge_all)


def on_page_published(sender, instance, **kwargs):
    """Purge the published page (and its parent IndexPage if applicable)."""
    logger.debug(
        "wtrx signals: page_published (%s pk=%s) — triggering purge_page_with_related.",
        sender.__name__,
        instance.pk,
    )
    transaction.on_commit(lambda: purge_page_with_related(instance))


def on_page_unpublished(sender, instance, **kwargs):
    """Purge the unpublished page (and its parent IndexPage if applicable)."""
    logger.debug(
        "wtrx signals: page_unpublished (%s pk=%s) — triggering purge_page_with_related.",
        sender.__name__,
        instance.pk,
    )
    transaction.on_commit(lambda: purge_page_with_related(instance))


def on_page_slug_changed(sender, instance, instance_before=None, **kwargs):
    """Purge both the old URL (pre-slug-change) and the new URL.

    ``instance_before`` is provided by Wagtail's ``page_slug_changed`` signal
    and holds the page state before the slug was changed. Its ``get_full_url()``
    resolves the now-stale old URL so the CDN can evict it.
    """
    logger.debug(
        "wtrx signals: page_slug_changed (%s pk=%s) — purging old and new URLs.",
        sender.__name__,
        instance.pk,
    )
    old_url = instance_before.get_full_url() if instance_before is not None else None
    extra_urls = [old_url] if old_url else None
    transaction.on_commit(lambda: purge_page_with_related(instance, extra_urls=extra_urls))


def connect_signals():
    """Connect all wtrx signal handlers.

    Called from WtrxConfig.ready(), once the app registry is populated.
    Settings models are discovered from the registry rather than listed by
    hand, so a newly added ``BaseSiteSetting`` purges the cache without anyone
    remembering to register it here.
    """
    from django.apps import apps
    from django.db.models.signals import post_save
    from wagtail.contrib.settings.models import BaseSiteSetting

    settings_models = [
        model for model in apps.get_app_config("wtrx").get_models() if issubclass(model, BaseSiteSetting)
    ]
    for model in settings_models:
        post_save.connect(
            on_settings_saved,
            sender=model,
            dispatch_uid=f"wtrx_cache_purge_all_{model.__name__}",
        )

    page_published.connect(
        on_page_published, dispatch_uid="wtrx.signals.on_page_published"
    )
    page_unpublished.connect(
        on_page_unpublished, dispatch_uid="wtrx.signals.on_page_unpublished"
    )
    page_slug_changed.connect(
        on_page_slug_changed, dispatch_uid="wtrx.signals.on_page_slug_changed"
    )

"""
Django signal handlers for wtrx cache invalidation.

Registered in WtrxConfig.ready() (wtrx/apps.py).

- ``on_settings_saved`` — connected to ``post_save`` for all 5 site settings
  models. Any settings save triggers a full-site purge because header/footer
  content appears on every page.
- ``on_page_published`` — connected to Wagtail's ``page_published`` signal.
  Purges the published page and its parent IndexPage (if applicable) to keep
  listing pages fresh.
- ``on_page_unpublished`` — connected to Wagtail's ``page_unpublished`` signal.
  Purges the now-unpublished page and its parent IndexPage so stale entries
  are removed from listing pages.
- ``on_page_slug_changed`` — connected to Wagtail's ``page_slug_changed``
  signal. Purges both the old URL (via the page's cached pre-save URL) and the
  new URL so redirects and listing pages reflect the updated slug immediately.
"""

import logging

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
    purge_all()


def on_page_published(sender, instance, **kwargs):
    """Purge the published page (and its parent IndexPage if applicable)."""
    logger.debug(
        "wtrx signals: page_published (%s pk=%s) — triggering purge_page_with_related.",
        sender.__name__,
        instance.pk,
    )
    purge_page_with_related(instance)


def on_page_unpublished(sender, instance, **kwargs):
    """Purge the unpublished page (and its parent IndexPage if applicable)."""
    logger.debug(
        "wtrx signals: page_unpublished (%s pk=%s) — triggering purge_page_with_related.",
        sender.__name__,
        instance.pk,
    )
    purge_page_with_related(instance)


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
    purge_page_with_related(instance, extra_urls=[old_url] if old_url else None)


def connect_signals():
    """Connect all wtrx signal handlers.

    Called from WtrxConfig.ready(). Importing settings models here (inside the
    function) defers the import until after the app registry is fully populated,
    avoiding AppRegistryNotReady errors.
    """
    from django.db.models.signals import post_save

    from wtrx.site_settings import (
        BrandingSEOSettings,
        FooterSettings,
        IntegrationSettings,
        NavigationSettings,
        SocialSettings,
    )

    settings_models = [
        BrandingSEOSettings,
        NavigationSettings,
        FooterSettings,
        SocialSettings,
        IntegrationSettings,
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

"""
Wagtail hooks for the wtrx app.

Hooks registered here:
- register_admin_urls: adds the block-visibility JS endpoint
- insert_global_admin_js: loads the block-visibility script and the
  wagtail-ai context-handler fix in the admin
"""

import json

from django.http import HttpResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.staticfiles import versioned_static
from wagtail.admin.ui.sidebar import LinkMenuItem as LinkMenuItemComponent


# ---------------------------------------------------------------------------
# Block visibility — hide irrelevant block types in the StreamField editor
# ---------------------------------------------------------------------------
#
# All SignupBlock and DonateBlock variants are always registered in
# BodyStreamBlock (see blocks/__init__.py). This hook hides the block-type
# picker buttons for integrations that aren't enabled in the site's
# IntegrationSettings. Which content block(s) each integration gates is
# metadata on its IntegrationType (wtrx/integrations/registry.py) —
# adding a new integration type never requires touching this file.
#
# signup_wagtail_forms and signup_link are not gated by any integration —
# they're always visible (the built-in form and a plain CTA link work
# regardless of which integrations are enabled).
#
# How it works:
#   1. register_admin_urls adds a lightweight JS endpoint at
#      /admin/wtrx/block-visibility.js that reads IntegrationSettings
#      for the current request's site and returns a script that hides
#      the irrelevant block-chooser buttons via CSS.
#   2. insert_global_admin_js injects a <script> tag loading that endpoint
#      on every admin page.
#
# This approach avoids reading the database at import time (architecture
# rule #4 in AGENTS.md) — the DB is only queried when the admin page is
# actually loaded.
# ---------------------------------------------------------------------------


def _block_visibility_js(request):
    """
    Return a JS snippet that hides block-type buttons in the StreamField
    block chooser for disabled integrations.

    The script injects a <style> element with CSS rules that hide the
    block-chooser buttons for disabled block types. CSS injection works
    reliably with Wagtail's dynamic Telepath/React rendering because
    the style rules apply whenever matching DOM elements appear.
    """
    # Import here to avoid import-time DB access
    from wagtail.models import Site

    from wtrx.integrations.registry import all_integrations
    from wtrx.site_settings import IntegrationSettings

    try:
        integration = IntegrationSettings.for_request(request)
        hidden_blocks = [
            block_name
            for integration_type in all_integrations()
            if not integration.is_integration_enabled(integration_type.slug)
            for block_name in integration_type.content_block_names
        ]
    except (IntegrationSettings.DoesNotExist, Site.DoesNotExist):
        # If settings aren't configured yet (fresh install), show all blocks
        hidden_blocks = []

    if not hidden_blocks:
        # Nothing to hide — return a no-op script
        js = "/* wtrx: all block types visible */"
    else:
        # Build CSS selectors that target the block-type buttons.
        # [data-contentpath="<name>"] targets existing block instances in the
        # StreamField editor. button[data-type="<name>"] targets the block-type
        # buttons in the add-block chooser panel.
        selectors = []
        for name in hidden_blocks:
            selectors.append(f'[data-contentpath="{name}"]')
            selectors.append(f'button[data-type="{name}"]')
        css_text = ", ".join(selectors) + " { display: none !important; }"

        js = f"""
(function() {{
    var style = document.createElement('style');
    style.textContent = {json.dumps(css_text)};
    document.head.appendChild(style);
}})();
"""

    return HttpResponse(js, content_type="application/javascript")


@hooks.register("register_admin_urls")
def register_block_visibility_url():
    return [
        path(
            "wtrx/block-visibility.js",
            _block_visibility_js,
            name="wtrx_block_visibility_js",
        ),
    ]


@hooks.register("insert_global_admin_js")
def insert_block_visibility_js():
    url = reverse("wtrx_block_visibility_js")
    return format_html('<script src="{}"></script>', url)


# ---------------------------------------------------------------------------
# wagtail-ai context-handler fix — see the file itself for the full
# explanation. Remove both this hook and the static file once wagtail-ai
# ships a release that awaits PreviewController.extractContent().
# ---------------------------------------------------------------------------


@hooks.register("insert_global_admin_js")
def insert_wagtail_ai_context_fix_js():
    return format_html(
        '<script src="{}"></script>',
        versioned_static("wtrx/admin/wagtail-ai-context-fix.js"),
    )


# ---------------------------------------------------------------------------
# Draftail toolbar — default to pinned for editors who haven't set a
# preference yet. See the file itself for the full explanation.
# ---------------------------------------------------------------------------


@hooks.register("insert_global_admin_js")
def insert_pin_draftail_toolbar_js():
    return format_html(
        '<script src="{}"></script>',
        versioned_static("wtrx/admin/pin-draftail-toolbar.js"),
    )


# Credential-field show/hide is no longer needed: each integration's fields
# now live inside its own StreamField block instance in IntegrationSettings,
# so Wagtail's editor already only shows the fields for integrations an
# admin has actually added.


# ---------------------------------------------------------------------------
# Blog admin-menu shortcut
# ---------------------------------------------------------------------------
#
# Adds a "Blog" item to the admin sidebar linking to the page explorer for
# the blog index page configured in Settings > Admin menu
# (AdminMenuSettings.blog_index_page). Hidden entirely when no blog index
# page is configured, or the configured page isn't live.
# ---------------------------------------------------------------------------


def _get_blog_index_page(request):
    # Import here to avoid import-time DB access
    from wagtail.models import Site

    from wtrx.site_settings import AdminMenuSettings

    try:
        admin_settings = AdminMenuSettings.for_request(request)
    except (AdminMenuSettings.DoesNotExist, Site.DoesNotExist):
        return None

    page = admin_settings.blog_index_page
    if page is None or not page.live:
        return None
    return page


class BlogMenuItem(MenuItem):
    def is_shown(self, request):
        return _get_blog_index_page(request) is not None

    def render_component(self, request):
        # Recompute rather than reuse a cached URL: menu item instances are
        # shared across requests, so the target page must be resolved fresh
        # each time rather than stashed on self.
        page = _get_blog_index_page(request)
        url = reverse("wagtailadmin_explore", args=[page.id])
        return LinkMenuItemComponent(
            self.name,
            self.label,
            url,
            icon_name=self.icon_name,
            classname=self.classname,
            attrs=self.attrs,
        )


@hooks.register("register_admin_menu_item")
def register_blog_menu_item():
    return BlogMenuItem(
        _("Blog"),
        "#",
        name="blog",
        icon_name="doc-empty",
        order=150,
    )

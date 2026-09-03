"""
Wagtail hooks for the wtrx app.

Hooks registered here:
- insert_global_admin_js: loads the wagtail-ai context-handler fix and the
  pinned-Draftail-toolbar default in the admin
- insert_global_admin_css: loads the 350.org admin theme colours (see
  wtrx/static/wtrx/admin/branding.css)
- construct_main_menu: adds the configurable admin sidebar shortcuts from
  AdminMenuSettings.sidebar_shortcuts (Settings > Admin menu)
- construct_settings_menu: groups Branding & SEO / Navigation / Footer /
  Social under one "Site design" flyout in the Settings menu, so the
  Settings sidebar doesn't grow one flat entry per settings model forever

Block-type visibility (hiding irrelevant SignupBlock/DonateBlock variants
per IntegrationSettings) is NOT a hook — it lives in
IntegrationGatedStreamBlockMixin in wtrx/blocks/__init__.py, which filters
BodyStreamBlock/SectionContentBlock's "Add block" picker natively via
sorted_child_blocks(), plus GatedStreamBlockAdapter (also in
wtrx/blocks/__init__.py), a telepath Adapter that keeps an already-placed
instance of a gated block hydrating/rendering correctly in the editor even
after its integration is later disabled. See wtrx/request_context.py for
how block code accesses the current request.
"""

from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from wagtail import hooks
from wagtail.admin.menu import Menu, MenuItem, SubmenuMenuItem
from wagtail.admin.staticfiles import versioned_static
from wagtail.contrib.settings.registry import SettingMenuItem

from wtrx.site_settings import (
    BrandingSEOSettings,
    FooterSettings,
    NavigationSettings,
    SocialSettings,
)


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


# ---------------------------------------------------------------------------
# Admin theme colours — 350.org brand blue/navy in place of Wagtail's
# defaults, via the CSS custom properties Wagtail documents for this
# (https://docs.wagtail.org/en/stable/advanced_topics/customization/admin_templates.html#custom-colours).
# See the file itself for the exact values and where they come from.
# ---------------------------------------------------------------------------


@hooks.register("insert_global_admin_css")
def insert_admin_branding_css():
    return format_html(
        '<link rel="stylesheet" href="{}">',
        versioned_static("wtrx/admin/branding.css"),
    )


# Credential-field show/hide is no longer needed: each integration's fields
# now live inside its own StreamField block instance in IntegrationSettings,
# so Wagtail's editor already only shows the fields for integrations an
# admin has actually added.


# ---------------------------------------------------------------------------
# Admin sidebar shortcuts (Settings > Admin menu)
# ---------------------------------------------------------------------------
#
# Was two hardcoded fields (blog_index_page, press_releases_index_page),
# each with its own MenuItem subclass and register_admin_menu_item hook —
# see git history for that version. AdminMenuSettings.sidebar_shortcuts is
# now a StreamField list of (label, page, icon) entries, so this needs to
# add a *variable* number of menu items depending on what's configured —
# register_admin_menu_item hooks each return exactly one item (see
# wagtail.admin.menu.Menu.registered_menu_items, `items.append(fn())`), so
# that mechanism can't produce N items from one hook. construct_main_menu
# is the right hook instead: it receives the already-assembled `items` list
# for the current request and can append any number of entries to it.
#
# Because this hook runs per-request (not once at import time), each
# MenuItem built here is a fresh instance scoped to this request — unlike
# the old BlogMenuItem/PressReleasesMenuItem, there's no shared/cached
# instance to worry about resolving stale data on.
# ---------------------------------------------------------------------------


@hooks.register("construct_main_menu")
def add_admin_menu_shortcuts(request, items):
    # Imports here to avoid import-time DB access (AGENTS.md pitfall #1).
    from wagtail.models import Site

    from wtrx.site_settings import AdminMenuSettings

    try:
        admin_settings = AdminMenuSettings.for_request(request)
    except (AdminMenuSettings.DoesNotExist, Site.DoesNotExist):
        return

    for index, shortcut in enumerate(admin_settings.sidebar_shortcuts):
        page = shortcut.value.get("page")
        if page is None or not page.live:
            continue
        label = shortcut.value.get("label") or page.title
        icon_name = shortcut.value.get("icon") or "doc-empty"
        items.append(
            MenuItem(
                label,
                reverse("wagtailadmin_explore", args=[page.id]),
                name=f"admin-menu-shortcut-{index}",
                icon_name=icon_name,
                order=150 + index,
            )
        )


# ---------------------------------------------------------------------------
# Settings menu grouping
# ---------------------------------------------------------------------------
#
# Wagtail's own Settings entry (wagtail/admin/wagtail_hooks.py,
# SettingsMenuItem) is a SubmenuMenuItem wrapping a Menu that itself
# supports a construct_settings_menu hook — the same items-list-mutation
# pattern construct_main_menu above uses, just for the Settings flyout
# instead of the top-level sidebar. Every @register_setting(...) model
# (site_settings.py) registers a flat SettingMenuItem in that list via
# Wagtail's own registry (wagtail.contrib.settings.registry.Registry.register),
# so without this hook the Settings flyout grows one entry per settings
# model forever. This groups the site-identity/presentation models — the
# ones an editor thinks of as "how the site looks" — under one "Site
# design" flyout, leaving Integrations and Admin menu (more
# operational/technical) at the top level.
#
# Matching by `item.model` (SettingMenuItem stores the registered model on
# itself) rather than by label/slug — robust to a verbose_name changing
# later, and avoids re-deriving Wagtail's own slugification.
# ---------------------------------------------------------------------------

_SITE_DESIGN_SETTINGS_MODELS = {
    BrandingSEOSettings,
    NavigationSettings,
    FooterSettings,
    SocialSettings,
}


@hooks.register("construct_settings_menu")
def group_site_design_settings_menu_items(request, items):
    grouped = [
        item
        for item in items
        if isinstance(item, SettingMenuItem) and item.model in _SITE_DESIGN_SETTINGS_MODELS
    ]
    if not grouped:
        return

    for item in grouped:
        items.remove(item)

    items.append(
        SubmenuMenuItem(
            _("Site design"),
            Menu(items=grouped),
            name="site-design",
            icon_name="view",
            order=15,
        )
    )

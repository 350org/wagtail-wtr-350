"""
Wagtail hooks for the wtrx app.

Hooks registered here:
- insert_global_admin_js: loads the wagtail-ai context-handler fix and the
  pinned-Draftail-toolbar default in the admin

Block-type visibility (hiding irrelevant SignupBlock/DonateBlock variants
per IntegrationSettings) is NOT a hook — it lives in
IntegrationGatedStreamBlockMixin in wtrx/blocks/__init__.py, which filters
BodyStreamBlock/SectionContentBlock's "Add block" picker natively via
sorted_child_blocks(). See wtrx/request_context.py for how block code
accesses the current request.
"""

from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.staticfiles import versioned_static
from wagtail.admin.ui.sidebar import LinkMenuItem as LinkMenuItemComponent


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


# ---------------------------------------------------------------------------
# Press releases admin-menu shortcut
# ---------------------------------------------------------------------------
#
# Same pattern as the Blog shortcut above, pointing at
# AdminMenuSettings.press_releases_index_page instead.
# ---------------------------------------------------------------------------


def _get_press_releases_index_page(request):
    # Import here to avoid import-time DB access
    from wagtail.models import Site

    from wtrx.site_settings import AdminMenuSettings

    try:
        admin_settings = AdminMenuSettings.for_request(request)
    except (AdminMenuSettings.DoesNotExist, Site.DoesNotExist):
        return None

    page = admin_settings.press_releases_index_page
    if page is None or not page.live:
        return None
    return page


class PressReleasesMenuItem(MenuItem):
    def is_shown(self, request):
        return _get_press_releases_index_page(request) is not None

    def render_component(self, request):
        # Recompute rather than reuse a cached URL: menu item instances are
        # shared across requests, so the target page must be resolved fresh
        # each time rather than stashed on self.
        page = _get_press_releases_index_page(request)
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
def register_press_releases_menu_item():
    return PressReleasesMenuItem(
        _("Press releases"),
        "#",
        name="press-releases",
        icon_name="clipboard-list",
        order=151,
    )

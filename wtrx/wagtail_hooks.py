"""
Wagtail hooks for the wtrx app.

Hooks registered here:
- register_admin_urls: adds the block-visibility JS endpoint
- insert_global_admin_js: loads the block-visibility script and AN API key
  field visibility script in the admin
"""

import json

from django.http import HttpResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.ui.sidebar import LinkMenuItem as LinkMenuItemComponent


# ---------------------------------------------------------------------------
# Block visibility — hide irrelevant block types in the StreamField editor
# ---------------------------------------------------------------------------
#
# All SignupBlock and DonateBlock variants are always registered in
# BodyStreamBlock (see blocks/__init__.py). This hook hides the block-type
# picker buttons for variants that are irrelevant based on the site's
# IntegrationSettings.
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

# Mapping of block type names (as registered in BodyStreamBlock) to the
# platform setting that must be active for the block to be visible.
# Blocks not listed here are always visible.
BLOCK_PLATFORM_REQUIREMENTS = {
    # Donation blocks — visible when donation_platform != "none"
    "donate": ("donation", None),
    # Signup blocks — visible when signup_platform is one of the listed values.
    # The Wagtail-forms block also renders the form for the ActionKit platform
    # (ActionKit forwarding happens server-side in FormPage.process_form_submission),
    # so it must be available under both.
    "signup_wagtail_forms": ("signup", ("wagtail_forms", "actionkit")),
    "signup_action_network": ("signup", ("action_network",)),
    # signup_link is always visible (it's a simple CTA link, platform-agnostic)
}


def _block_visibility_js(request):
    """
    Return a JS snippet that hides block-type buttons in the StreamField
    block chooser for irrelevant platform variants.

    The script injects a <style> element with CSS rules that hide the
    block-chooser buttons for disabled block types. CSS injection works
    reliably with Wagtail's dynamic Telepath/React rendering because
    the style rules apply whenever matching DOM elements appear.
    """
    # Import here to avoid import-time DB access
    from wagtail.models import Site

    from wtrx.site_settings import IntegrationSettings

    try:
        integration = IntegrationSettings.for_request(request)
        donation_platform = integration.get_donation_platform()
        signup_platform = integration.get_signup_platform()
    except (IntegrationSettings.DoesNotExist, Site.DoesNotExist):
        # If settings aren't configured yet (fresh install), show all blocks
        donation_platform = "none"
        signup_platform = "wagtail_forms"

    hidden_blocks = []

    for block_name, (category, required_value) in BLOCK_PLATFORM_REQUIREMENTS.items():
        if category == "donation":
            if donation_platform == "none":
                hidden_blocks.append(block_name)
        elif category == "signup":
            if signup_platform not in required_value:
                hidden_blocks.append(block_name)

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
# Signup-platform credential field visibility
# ---------------------------------------------------------------------------
#
# Shows each platform's credential fields in IntegrationSettings only when that
# platform is the selected signup_platform: the Action Network API key for
# "action_network", and the ActionKit host/username/password for "actionkit".
# Uses a MutationObserver so it works with Wagtail's dynamic form rendering.
# ---------------------------------------------------------------------------

_SIGNUP_PLATFORM_FIELD_JS = """
(function () {
    var PLATFORM_FIELDS = {
        action_network: ["action_network_api_key"],
        actionkit: ["actionkit_hostname", "actionkit_api_username", "actionkit_api_password"]
    };

    function fieldWrapper(name) {
        var input = document.querySelector('[data-field-input-name="' + name + '"]');
        if (!input) { return null; }
        return input.closest('[data-field]') || input.closest('.w-field__wrapper') || input.parentElement;
    }

    function updateVisibility() {
        var platformField = document.querySelector('[name="signup_platform"]');
        if (!platformField) { return; }
        var selected = platformField.value;
        Object.keys(PLATFORM_FIELDS).forEach(function (platform) {
            var show = platform === selected;
            PLATFORM_FIELDS[platform].forEach(function (name) {
                var wrapper = fieldWrapper(name);
                if (wrapper) { wrapper.style.display = show ? '' : 'none'; }
            });
        });
    }

    function init() {
        updateVisibility();
        var form = document.querySelector('form[data-edit-form], form.w-settings-form, form');
        if (form) {
            form.addEventListener('change', function (e) {
                if (e.target && e.target.name === 'signup_platform') {
                    updateVisibility();
                }
            });
        }
        // MutationObserver handles dynamic form injection (Wagtail admin SPA navigation)
        var observer = new MutationObserver(function (mutations) {
            for (var i = 0; i < mutations.length; i++) {
                if (mutations[i].addedNodes.length) {
                    updateVisibility();
                    break;
                }
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
"""


@hooks.register("insert_global_admin_js")
def insert_signup_platform_field_visibility_js():
    return format_html("<script>{}</script>", _SIGNUP_PLATFORM_FIELD_JS)


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

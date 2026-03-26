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

from wagtail import hooks


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
    # Signup blocks — visible when signup_platform matches
    "signup_wagtail_forms": ("signup", "wagtail_forms"),
    "signup_action_network": ("signup", "action_network"),
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

    from wagtail_wtr.wtrx.site_settings import IntegrationSettings

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
            if signup_platform != required_value:
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
# Action Network API key field visibility
# ---------------------------------------------------------------------------
#
# Hides the action_network_api_key field in IntegrationSettings unless
# signup_platform is set to "action_network". Uses a MutationObserver so
# it works with Wagtail's dynamic form rendering.
# ---------------------------------------------------------------------------

_AN_API_KEY_JS = """
(function () {
    function updateApiKeyVisibility() {
        var platformField = document.querySelector('[name="signup_platform"]');
        var apiKeyRow = document.querySelector('[data-field-input-name="action_network_api_key"]');
        if (!platformField || !apiKeyRow) {
            return;
        }
        var wrapper = apiKeyRow.closest('[data-field]') || apiKeyRow.closest('.w-field__wrapper') || apiKeyRow.parentElement;
        if (wrapper) {
            wrapper.style.display = platformField.value === 'action_network' ? '' : 'none';
        }
    }

    function init() {
        updateApiKeyVisibility();
        var form = document.querySelector('form[data-edit-form], form.w-settings-form, form');
        if (form) {
            form.addEventListener('change', function (e) {
                if (e.target && e.target.name === 'signup_platform') {
                    updateApiKeyVisibility();
                }
            });
        }
        // MutationObserver handles dynamic form injection (Wagtail admin SPA navigation)
        var observer = new MutationObserver(function (mutations) {
            for (var i = 0; i < mutations.length; i++) {
                if (mutations[i].addedNodes.length) {
                    updateApiKeyVisibility();
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
def insert_an_api_key_visibility_js():
    return format_html("<script>{}</script>", _AN_API_KEY_JS)

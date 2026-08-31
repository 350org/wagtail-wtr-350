"""
Fundraise Up integration — donation button embed, no server-side API calls.

Fundraise Up elements (buttons, forms, overlays) are created in Fundraise Up's
own dashboard, each yielding an opaque Element ID. Embedding one is just a
hidden anchor tag that Fundraise Up's installation script (rendered site-wide
in <head> via IntegrationSettings.head_html() when this integration is
enabled) scans for and hydrates into a styled checkout-modal trigger. See
DonateFundraiseUpBlock in wtrx/blocks/__init__.py for the block itself.

Region-based form geolocation
------------------------------
DonateFundraiseUpBlock always shows a region-specific Fundraise Up element,
configured here rather than per-block (a deliberate product decision — every
donate block on the site shows the same regional form, there is no per-block
override). The visitor's region is resolved **client-side**, not server-side:
this site fronts every page with Cloudflare's edge cache
(WAGTAILFRONTENDCACHE), so a page rendered with one visitor's country baked
into the HTML would get cached and served to every other visitor regardless
of their own country. The donate block's own inline script resolves the
visitor's country via Cloudflare's `/cdn-cgi/trace` edge endpoint (never
reaches Django, so it can't poison the page cache) and swaps the anchor's
target element ID client-side — the same approach already used for
Usercentrics' country-gated consent banner (see
wtrx/templates/wtrx/includes/usercentrics_head.html), reimplemented here
rather than shared with it: the two have different fallback semantics
(Usercentrics fails closed to an EU country for compliance; this fails open
to `element_id_default`) and touching consent-banner code for an unrelated
donation-forms feature isn't worth the coupling.

Fundraise Up's own installation script (loaded unconditionally in <head> via
head_html_field below) is deliberately **not** deferred to wait for that
client-side lookup to resolve first — the two run concurrently. Fundraise Up
scans the page for anchors and hydrates them on its own schedule; if that
scan happens to run before the /cdn-cgi/trace fetch resolves, the visitor
sees `element_id_default` (the anchor's server-rendered initial href, safe to
cache since it's the same for every visitor) rather than their own region's
form — never a broken state, just the non-regional default. Deferring
Fundraise Up's script to eliminate that race entirely (mirroring how
usercentrics_head.html defers loading the Usercentrics script until country
is known) was considered and deliberately not done, to keep Fundraise Up
loading exactly as fast as it does today.
"""

from django.utils.translation import gettext_lazy as _
from wagtail.blocks import BooleanBlock, CharBlock, StructBlock, TextBlock

from wtrx.integrations.registry import IntegrationType, register_integration


class FundraiseUpConfigBlock(StructBlock):
    """Per-site Fundraise Up configuration, added as an entry in Settings > Integrations."""

    enabled = BooleanBlock(
        required=False,
        default=True,
        label=_("Enabled"),
        help_text=_("Uncheck to temporarily disable Fundraise Up without removing its configuration."),
    )
    installation_code = TextBlock(
        label=_("Fundraise Up installation code"),
        help_text=_(
            "The full <script> snippet from your Fundraise Up dashboard "
            "(Settings → Installation). Rendered once in the site's <head> "
            "while Fundraise Up is enabled."
        ),
    )
    element_id_us = CharBlock(
        required=False,
        label=_("Form ID — United States visitors"),
        help_text=_("Fundraise Up element ID shown to visitors geolocated to the United States."),
    )
    element_id_nl = CharBlock(
        required=False,
        label=_("Form ID — Netherlands visitors"),
        help_text=_("Fundraise Up element ID shown to visitors geolocated to the Netherlands."),
    )
    element_id_ca = CharBlock(
        required=False,
        label=_("Form ID — Canada visitors"),
        help_text=_("Fundraise Up element ID shown to visitors geolocated to Canada."),
    )
    element_id_gb = CharBlock(
        required=False,
        label=_("Form ID — United Kingdom visitors"),
        help_text=_("Fundraise Up element ID shown to visitors geolocated to the United Kingdom."),
    )
    eu_country_codes = CharBlock(
        required=False,
        label=_("Other European country codes"),
        help_text=_(
            "Comma-separated two-letter ISO country codes (e.g. DE,FR,ES,IT) "
            "that should use the \"other European visitors\" form ID below. "
            "Do not include Netherlands or United Kingdom — they're "
            "configured separately above."
        ),
    )
    element_id_eu = CharBlock(
        required=False,
        label=_("Form ID — all other European visitors"),
        help_text=_(
            "Shown to visitors geolocated to a country listed above under "
            "\"Other European country codes\"."
        ),
    )
    element_id_default = CharBlock(
        required=False,
        label=_("Form ID — all other visitors"),
        help_text=_(
            "Shown to every visitor not covered by a region above, and as "
            "the form's initial state before the visitor's country is known "
            "or if it can't be determined (e.g. local development)."
        ),
    )

    class Meta:
        icon = "cogs"
        label = _("Fundraise Up")


register_integration(
    IntegrationType(
        slug="fundraiseup",
        label=_("Fundraise Up"),
        category="donation",
        content_block_names=("donate_fundraiseup",),
        head_html_field="installation_code",
    )
)

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
DonateFundraiseUpBlock shows a region-specific Fundraise Up element, whose
map is configured here as the site-wide default. A block can optionally
override individual regions for itself via its collapsed "Advanced
settings" section (FundraiseUpAdvancedSettingsBlock, wtrx/blocks/__init__.py)
— each of its fields falls through to this site-wide config when left
blank, so most donate blocks never touch it and behave exactly as before;
it exists for the occasional campaign-specific block that needs a
different form for one region, or a single fixed element regardless of
region (fill in every region field the same way). The visitor's region is
resolved **client-side**, not server-side:
this site fronts every page with Cloudflare's edge cache
(WAGTAILFRONTENDCACHE), so a page rendered with one visitor's country baked
into the HTML would get cached and served to every other visitor regardless
of their own country. The donate block's own inline script resolves the
visitor's country via Cloudflare's `/cdn-cgi/trace` edge endpoint (never
reaches Django, so it can't poison the page cache) and only then inserts the
anchor for that region's element — the same approach already used for
Usercentrics' country-gated consent banner (see
wtrx/templates/wtrx/includes/usercentrics_head.html), reimplemented here
rather than shared with it: the two have different fallback semantics
(Usercentrics fails closed to an EU country for compliance; this fails open
to `element_id_default`) and touching consent-banner code for an unrelated
donation-forms feature isn't worth the coupling.

Fundraise Up's own installation script (loaded unconditionally in <head> via
head_html_field below) is not deferred; the anchor is. Fundraise Up replaces
an anchor with its form as soon as it finds one, and keeps watching for
anchors added later, so the anchor must not exist until the region is known.
It used to be server-rendered with `element_id_default` and swapped
client-side afterwards, which lost whenever Fundraise Up got there first:
the default form was already in place, and the swap changed the href of an
anchor Fundraise Up had already consumed. The anchor now
appears once the lookup answers; if it fails (no Cloudflare in front, as on
staging and in local development) or takes longer than the template's
LOOKUP_TIMEOUT_MS, `element_id_default` is inserted instead.

`?fundraiseup_country=<ISO code>` on a page URL skips the lookup and shows
that region's form, for QA without a VPN — and the only way to check the
regions at all on an environment Cloudflare doesn't front.
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
            "The full script snippet from your Fundraise Up dashboard "
            "(Settings → Installation). Rendered once in the site's page "
            "head while Fundraise Up is enabled."
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

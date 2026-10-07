"""
Usercentrics integration -- consent management banner.

Unlike every other integration, this one is NOT rendered via
IntegrationType.head_html_field: that mechanism concatenates fragments at the
very END of <head> (Fundraise Up's own install docs require that placement),
while Usercentrics' Consent Mode v2 defaults must run before anything else
that could set analytics/ad cookies -- i.e. before everything else in <head>.
wtrx/templates/wtrx/includes/usercentrics_head.html reads this integration's
config directly via IntegrationSettings.get_usercentrics_config() and renders
it as the first scripts in <head> instead.

Visitor country is resolved entirely client-side via Cloudflare's
/cdn-cgi/trace edge endpoint (see the template for the full rationale), so
this integration makes no server-side API calls of its own.
"""

from django.utils.translation import gettext_lazy as _
from wagtail.blocks import BooleanBlock, CharBlock, StructBlock

from wtrx.integrations.registry import IntegrationType, register_integration


class UsercentricsConfigBlock(StructBlock):
    """Per-site Usercentrics configuration, added as an entry in Settings > Integrations."""

    enabled = BooleanBlock(
        required=False,
        default=True,
        label=_("Enabled"),
        help_text=_("Uncheck to temporarily disable the Usercentrics consent banner."),
    )
    settings_id = CharBlock(
        label=_("Settings ID"),
        help_text=_('The "Settings ID" from your Usercentrics dashboard.'),
    )
    script_version = CharBlock(
        default="1.1.4",
        label=_("Script version"),
        help_text=_(
            "Version of usercentrics-consent.js to load, from "
            "cdn.350.org/usercentrics-consent/<version>/usercentrics-consent.js."
        ),
    )
    reload_on_opt_in_service_ids = CharBlock(
        required=False,
        label=_("Reload-on-opt-in service IDs"),
        help_text=_(
            "Comma-separated Usercentrics service IDs that should reload the "
            "page when a visitor opts in to them."
        ),
    )
    deactivate_blocking_service_ids = CharBlock(
        required=False,
        label=_("Deactivate-blocking service IDs"),
        help_text=_(
            "Comma-separated Usercentrics service IDs whose default script "
            "blocking should be deactivated."
        ),
    )
    fallback_country = CharBlock(
        default="DE",
        max_length=2,
        label=_("Fallback country"),
        help_text=_(
            "Two-letter country code used when the visitor's country can't "
            "be determined (e.g. the geolocation lookup times out). Defaults "
            "to an EU country so the compliance banner fails closed (shows) "
            "rather than silently hiding."
        ),
    )
    manual_country_override = CharBlock(
        required=False,
        max_length=2,
        label=_("Manual country override (testing only)"),
        help_text=_(
            "Two-letter country code to force for every visitor, skipping "
            "the automatic Cloudflare geolocation lookup entirely. For "
            "QA/testing of a specific country only -- leave blank in "
            "production so each visitor's real country is used."
        ),
    )

    class Meta:
        icon = "cogs"
        label = _("Usercentrics")


register_integration(
    IntegrationType(
        slug="usercentrics",
        label=_("Usercentrics"),
        category="consent",
    )
)

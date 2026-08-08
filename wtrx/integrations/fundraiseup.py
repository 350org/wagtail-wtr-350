"""
Fundraise Up integration — donation button embed, no server-side API calls.

Fundraise Up elements (buttons, forms, overlays) are created in Fundraise Up's
own dashboard, each yielding an opaque Element ID. Embedding one is just a
hidden anchor tag that Fundraise Up's installation script (rendered site-wide
in <head> via IntegrationSettings.head_html() when this integration is
enabled) scans for and hydrates into a styled checkout-modal trigger. See
DonateFundraiseUpBlock in wtrx/blocks/__init__.py for the block itself.
"""

from django.utils.translation import gettext_lazy as _
from wagtail.blocks import BooleanBlock, StructBlock, TextBlock

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

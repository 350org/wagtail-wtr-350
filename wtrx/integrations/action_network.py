"""
Action Network integration — form embed widget, with an optional API key
reserved for future server-side use.

SignupActionNetworkBlock (wtrx/blocks/__init__.py) embeds an Action Network
form directly from a pasted URL and does not need the API key. The key is
kept here for future server-side Action Network calls (e.g. submission
forwarding, mirroring how ActionKit forwarding works).
"""

from django.utils.translation import gettext_lazy as _
from wagtail.blocks import BooleanBlock, CharBlock, StructBlock

from wtrx.integrations.registry import IntegrationType, register_integration


class ActionNetworkConfigBlock(StructBlock):
    """Per-site Action Network configuration, added as an entry in Settings > Integrations."""

    enabled = BooleanBlock(
        required=False,
        default=True,
        label=_("Enabled"),
        help_text=_("Uncheck to temporarily disable Action Network without removing its configuration."),
    )
    api_key = CharBlock(
        required=False,
        label=_("Action Network API key"),
        help_text=_(
            "Required for server-side Action Network integrations. "
            "Leave blank if using the embed widget approach."
        ),
    )

    class Meta:
        icon = "cogs"
        label = _("Action Network")


register_integration(
    IntegrationType(
        slug="action_network",
        label=_("Action Network"),
        category="signup",
        content_block_names=("signup_action_network",),
    )
)

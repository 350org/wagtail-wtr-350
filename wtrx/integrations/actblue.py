"""
ActBlue integration — generic hosted donation page, no API calls.

DonateBlock (wtrx/blocks/__init__.py) links out to an ActBlue (or ActBlue-like)
donation page. This module holds only the per-site configuration (base URL,
suggested amounts, recurring default); DonateBlock reads it via
IntegrationSettings.get_integration_config("actblue") at render time.
"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from wagtail.blocks import BooleanBlock, CharBlock, StructBlock, URLBlock

from wtrx.integrations.registry import IntegrationType, register_integration


def validate_comma_separated_amounts(value):
    """Validate that value is a comma-separated list of positive numbers."""
    if value:
        try:
            parsed = [Decimal(x.strip()) for x in value.split(",") if x.strip()]
            if any(v <= 0 for v in parsed):
                raise ValidationError(_("All amounts must be greater than zero."))
        except InvalidOperation:
            raise ValidationError(
                _("Enter a comma-separated list of amounts, e.g. 10,25,50,100.")
            )


class ActBlueConfigBlock(StructBlock):
    """Per-site ActBlue configuration, added as an entry in Settings > Integrations."""

    enabled = BooleanBlock(
        required=False,
        default=True,
        label=_("Enabled"),
        help_text=_("Uncheck to temporarily disable ActBlue without removing its configuration."),
    )
    base_url = URLBlock(
        label=_("Donation base URL"),
        help_text=_(
            "e.g. https://secure.actblue.com/donate/mycampaign. "
            "Used by DonateBlock when no override URL is set."
        ),
    )
    suggested_amounts = CharBlock(
        required=False,
        label=_("Suggested donation amounts"),
        help_text=_(
            "Comma-separated integers, e.g. 10,25,50,100. "
            "Used by DonateBlock when no override amounts are set."
        ),
        validators=[validate_comma_separated_amounts],
    )
    default_recurring = BooleanBlock(
        required=False,
        default=False,
        label=_("Default to recurring donation"),
    )

    class Meta:
        icon = "cogs"
        label = _("ActBlue")


register_integration(
    IntegrationType(
        slug="actblue",
        label=_("ActBlue"),
        category="donation",
        content_block_names=("donate",),
    )
)

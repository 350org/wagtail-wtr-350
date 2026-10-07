"""
Wagtail Forms — the built-in, zero-configuration signup option.

Unlike every other module in this package, this isn't a third-party
integration: SignupWagtailFormsBlock (wtrx/blocks/__init__.py) just renders a
FormPage's own form inline and needs no external API, credentials, or
dashboard setup to work. It's registered here anyway, as a lightweight
pseudo-integration, purely to reuse the same block-visibility mechanism
(wagtail_hooks.py) that gates the real integrations — a site that only wants
one signup platform in its editor can hide this option the same way it hides
an unused third-party one, without wagtail_hooks.py needing a special case.

Because it works out of the box, this is the one registration in the
registry with default_enabled=True: SignupWagtailFormsBlock stays visible in
the "Add block" picker until an editor explicitly adds a "Wagtail Forms"
entry here with Enabled unchecked. See IntegrationType.default_enabled and
IntegrationSettings.is_integration_enabled() for how that default is applied.
"""

from django.utils.translation import gettext_lazy as _
from wagtail.blocks import BooleanBlock, StructBlock

from wtrx.integrations.registry import IntegrationType, register_integration


class WagtailFormsConfigBlock(StructBlock):
    """
    Per-site Wagtail Forms toggle, added as an entry in Settings > Integrations.

    Carries no configuration fields beyond `enabled` — there is nothing to
    configure. Adding this entry (with Enabled unchecked) is only ever done
    to *hide* the "Sign Up (Wagtail Forms)" block from the editor; the
    built-in form functionality itself is never affected by this setting.
    """

    enabled = BooleanBlock(
        required=False,
        default=True,
        label=_("Enabled"),
        help_text=_(
            "Uncheck to hide the built-in Wagtail Forms signup block from "
            "the page editor. This does not affect any FormPage that is "
            "already published — it only controls whether editors can add "
            "new Wagtail Forms signup blocks."
        ),
    )

    class Meta:
        icon = "form"
        label = _("Wagtail Forms")


register_integration(
    IntegrationType(
        slug="wagtail_forms",
        label=_("Wagtail Forms (built-in)"),
        category="signup",
        content_block_names=("signup_wagtail_forms",),
        default_enabled=True,
    )
)

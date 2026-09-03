"""
In-memory registry of pre-set integration types.

Each integration module (actionkit.py, fundraiseup.py, actblue.py,
action_network.py) registers one IntegrationType here at import time. This
module is pure Python with no Django model imports, so populating it at
import time is safe — see AGENTS.md pitfall #1 (never read the *database* at
import time; this registry never touches the database).

The registry only carries metadata used by wagtail_hooks.py (block
visibility) and IntegrationSettings (head-html rendering). It does not build
the `integrations` StreamField block list — that stays an explicit named
StreamBlock subclass in site_settings.py, matching the declarative-subclass
pattern already used by BodyStreamBlock/SectionContentBlock (see AGENTS.md
architecture rule #9) so fork sites can override individual integrations the
same way they override individual content blocks.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IntegrationType:
    """
    Metadata describing one pre-set integration.

    slug: matches both the registry key and the block name used for this
        integration's entry in IntegrationsStreamBlock (site_settings.py).
    label: human-readable name shown in the admin.
    category: "donation" or "signup". Used to group integrations for
        templates/hooks that care about a category as a whole; an editor may
        enable more than one integration in the same category at once.
    content_block_names: names of attributes on BodyStreamBlock /
        SectionContentBlock (wtrx/blocks/__init__.py) that should only be
        selectable in the StreamField editor while this integration is
        enabled. Empty for integrations that don't contribute a content
        block.
    head_html_field: name of a field on this integration's config StructBlock
        whose value should be rendered verbatim into the site's <head> when
        the integration is enabled (e.g. FundraiseUp's installation script).
        None for integrations that don't inject site-wide markup.
    body_html_field: same idea as head_html_field, but rendered verbatim
        immediately after <body> opens instead (base.html) — for markup
        that specifically has to run early in the body, e.g. Google Tag
        Manager's <noscript> fallback iframe. None for integrations that
        don't need this (most won't — head_html_field covers the common
        case of a vendor <script> tag).
    default_enabled: whether this integration/feature should read as
        *enabled* when no entry for it exists yet in
        IntegrationSettings.integrations at all. False (the default) is
        correct for every genuine third-party integration — ActionKit,
        Fundraise Up, ActBlue, Action Network all require an editor to
        explicitly add and configure an entry before their content block(s)
        make sense to show. Set True only for a built-in CMS feature that
        works with zero external configuration (e.g. Wagtail Forms, see
        wtrx/integrations/wagtail_forms.py) and should therefore stay visible
        in the editor out of the box, hideable only by an editor adding an
        explicit entry with enabled=False. An explicit entry always wins over
        this default in either direction — see
        IntegrationSettings.is_integration_enabled().

    Reserved for future use (not implemented yet, see PLAN.md): hero-section
    and navigation/footer contribution hooks. Adding those later means adding
    new optional fields here, not reshaping the registry.
    """

    slug: str
    label: str
    category: str
    content_block_names: tuple[str, ...] = field(default_factory=tuple)
    head_html_field: str | None = None
    body_html_field: str | None = None
    default_enabled: bool = False


_REGISTRY: dict[str, IntegrationType] = {}


def register_integration(integration_type: IntegrationType) -> None:
    if integration_type.slug in _REGISTRY:
        raise ValueError(f"Integration '{integration_type.slug}' is already registered.")
    _REGISTRY[integration_type.slug] = integration_type


def get_integration(slug: str) -> IntegrationType | None:
    return _REGISTRY.get(slug)


def all_integrations() -> list[IntegrationType]:
    return list(_REGISTRY.values())

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.blocks import (
    CharBlock,
    ChoiceBlock,
    PageChooserBlock,
    StreamBlock,
    StructBlock,
    URLBlock,
)
from wagtail.contrib.settings.models import BaseSiteSetting, register_setting
from wagtail.fields import StreamField

from .images import CustomImage
from .integrations.actblue import (
    ActBlueConfigBlock,
    validate_comma_separated_amounts,  # noqa: F401 -- referenced by historical migration 0001_initial
)
from .integrations.action_network import ActionNetworkConfigBlock
from .integrations.actionkit import ActionKitConfigBlock
from .integrations.fundraiseup import FundraiseUpConfigBlock
from .integrations.registry import all_integrations


# ---------------------------------------------------------------------------
# Navigation link blocks (used by NavigationSettings and FooterSettings)
# ---------------------------------------------------------------------------


class InternalLinkBlock(StructBlock):
    """A navigation link to an internal Wagtail page."""

    text = CharBlock(label=_("Link text"))
    page = PageChooserBlock(label=_("Page"))

    class Meta:
        icon = "link"
        label = _("Internal link")


class ExternalLinkBlock(StructBlock):
    """A navigation link to an external URL."""

    text = CharBlock(label=_("Link text"))
    url = URLBlock(label=_("URL"))

    class Meta:
        icon = "link"
        label = _("External link")


class AnchorLinkBlock(StructBlock):
    """A navigation link to an anchor on the current page (e.g. #about)."""

    text = CharBlock(label=_("Link text"))
    anchor = CharBlock(
        label=_("Anchor"),
        help_text=_("Anchor ID without the # symbol, e.g. 'about'."),
    )

    class Meta:
        icon = "link"
        label = _("Anchor link")


class SubmenuBlock(StructBlock):
    """A top-level navigation item that expands into a dropdown of child links."""

    text = CharBlock(label=_("Menu label"))
    links = StreamBlock(
        [
            ("internal", InternalLinkBlock()),
            ("external", ExternalLinkBlock()),
            ("anchor", AnchorLinkBlock()),
        ],
        label=_("Dropdown links"),
    )

    class Meta:
        icon = "list-ul"
        label = _("Dropdown menu")


class FooterColumnBlock(StructBlock):
    """A column of links in the footer."""

    heading = CharBlock(label=_("Column heading"), required=False)
    links = StreamBlock(
        [
            ("internal", InternalLinkBlock()),
            ("external", ExternalLinkBlock()),
            ("anchor", AnchorLinkBlock()),
        ],
        label=_("Links"),
    )

    class Meta:
        icon = "list-ul"
        label = _("Footer column")


# Module-level so it can be reused in templates/filters if needed.
SOCIAL_PLATFORM_CHOICES = [
    ("facebook", "Facebook"),
    ("twitter", "Twitter / X"),
    ("instagram", "Instagram"),
    ("tiktok", "TikTok"),
    ("linkedin", "LinkedIn"),
    ("youtube", "YouTube"),
    ("threads", "Threads"),
    ("bluesky", "Bluesky"),
    ("mastodon", "Mastodon"),
]


class SocialLinkBlock(StructBlock):
    """
    A single social media link.

    Explicitly named StructBlock subclass (not anonymous) so Django's migration
    serialization can reference it by dotted path.
    """

    platform = ChoiceBlock(choices=SOCIAL_PLATFORM_CHOICES, label=_("Platform"))
    url = URLBlock(label=_("URL"))

    class Meta:
        icon = "site"
        label = _("Social link")


# Module-level per AGENTS.md pitfall #10 — gettext_lazy in choices requires
# module-level definition to avoid migration serialization failures.
FOOTER_LAYOUT_CHOICES = [
    ("columns", _("Columns")),
    ("minimal", _("Minimal")),
]


# ---------------------------------------------------------------------------
# Settings panels
# ---------------------------------------------------------------------------


@register_setting(icon="image", order=10)
class BrandingSEOSettings(BaseSiteSetting):
    """Settings > Branding & SEO — logo, favicon, default meta image, site description."""

    logo = models.ForeignKey(
        CustomImage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("logo"),
        help_text=_("Primary site logo. Displayed in the header."),
    )
    dark_logo = models.ForeignKey(
        CustomImage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("dark logo"),
        help_text=_(
            "Logo variant for dark or transparent backgrounds (e.g. transparent header)."
        ),
    )
    favicon = models.ForeignKey(
        CustomImage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("favicon"),
        help_text=_("Browser favicon (square image, 32×32 px or SVG)."),
    )
    default_meta_image = models.ForeignKey(
        CustomImage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("default meta image"),
        help_text=_(
            "Fallback OG / Twitter card image used when a page has no meta image set."
        ),
    )
    site_description = models.TextField(
        blank=True,
        verbose_name=_("site description"),
        help_text=_("Default meta description for the site."),
    )

    panels = [
        MultiFieldPanel(
            [FieldPanel("logo"), FieldPanel("dark_logo"), FieldPanel("favicon")],
            heading=_("Logos"),
        ),
        MultiFieldPanel(
            [FieldPanel("default_meta_image"), FieldPanel("site_description")],
            heading=_("SEO defaults"),
        ),
    ]

    class Meta:
        verbose_name = _("Branding & SEO")


@register_setting(icon="list-ul", order=20)
class NavigationSettings(BaseSiteSetting):
    """Settings > Navigation — primary nav links, CTA button, layout options."""

    primary_navigation = StreamField(
        [
            ("internal", InternalLinkBlock()),
            ("external", ExternalLinkBlock()),
            ("anchor", AnchorLinkBlock()),
            ("submenu", SubmenuBlock()),
        ],
        blank=True,
        verbose_name=_("primary navigation"),
        help_text=_("Links shown in the main navigation bar."),
        use_json_field=True,
    )
    cta_text = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("CTA button text"),
        help_text=_("Text for the header call-to-action button."),
    )
    cta_page = models.ForeignKey(
        "wagtailcore.Page",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("CTA page"),
        help_text=_(
            "Internal link for the CTA button. Set either this or CTA URL, not both."
        ),
    )
    cta_url = models.URLField(
        blank=True,
        verbose_name=_("CTA URL"),
        help_text=_(
            "External link for the CTA button. Set either this or CTA page, not both."
        ),
    )
    cta_anchor = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("CTA anchor"),
        help_text=_(
            "Anchor link for the CTA button (without the # symbol, e.g. 'donate'). "
            "Set this instead of CTA page or CTA URL to link to an anchor on the current page."
        ),
    )
    collapse_desktop_menu = models.BooleanField(
        default=False,
        verbose_name=_("collapse desktop menu"),
        help_text=_(
            "Always show the hamburger menu icon, even on desktop. "
            "Navigation links are hidden behind the menu toggle at all screen sizes."
        ),
    )

    panels = [
        FieldPanel("primary_navigation"),
        MultiFieldPanel(
            [
                FieldPanel("cta_text"),
                FieldPanel("cta_page"),
                FieldPanel("cta_url"),
                FieldPanel("cta_anchor"),
            ],
            heading=_("CTA button"),
        ),
        MultiFieldPanel(
            [FieldPanel("collapse_desktop_menu")],
            heading=_("Layout"),
        ),
    ]

    def clean(self):
        errors = {}
        if (
            self.cta_text
            and not self.cta_page
            and not self.cta_url
            and not self.cta_anchor
        ):
            msg = _(
                "Set either a CTA page, CTA URL, or CTA anchor when CTA button text is provided."
            )
            errors["cta_page"] = msg
            errors["cta_url"] = msg
            errors["cta_anchor"] = msg
        cta_targets_set = sum(
            [
                bool(self.cta_page),
                bool(self.cta_url),
                bool(self.cta_anchor),
            ]
        )
        if cta_targets_set > 1:
            msg = _("Set only one of CTA page, CTA URL, or CTA anchor — not multiple.")
            errors["cta_url"] = msg
            errors["cta_anchor"] = msg
        if cta_targets_set > 0 and not self.cta_text:
            errors["cta_text"] = _(
                "CTA button text is required when a CTA page, URL, or anchor is set."
            )
        if errors:
            raise ValidationError(errors)

    class Meta:
        verbose_name = _("Navigation")


@register_setting(icon="bars", order=30)
class FooterSettings(BaseSiteSetting):
    """Settings > Footer — layout mode, footer nav columns, minimal links, copyright text."""

    layout = models.CharField(
        max_length=20,
        choices=FOOTER_LAYOUT_CHOICES,
        default="columns",
        verbose_name=_("footer layout"),
        help_text=_(
            "Columns: multi-column navigation grid. "
            "Minimal: single-row bar with logo, copyright, social icons, and inline links."
        ),
    )
    footer_navigation = StreamField(
        [("column", FooterColumnBlock())],
        blank=True,
        verbose_name=_("footer navigation"),
        help_text=_(
            "Footer link columns. Each column has a heading and a list of links."
        ),
        use_json_field=True,
    )
    minimal_links = StreamField(
        [
            ("internal", InternalLinkBlock()),
            ("external", ExternalLinkBlock()),
            ("anchor", AnchorLinkBlock()),
        ],
        blank=True,
        verbose_name=_("minimal footer links"),
        help_text=_(
            "Flat list of links displayed inline in the minimal footer layout."
        ),
        use_json_field=True,
    )
    copyright_text = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("copyright text"),
        help_text=_(
            'Optional. Overrides the default "© {year} {site name}" copyright line.'
        ),
    )

    panels = [
        FieldPanel("layout"),
        MultiFieldPanel(
            [FieldPanel("footer_navigation")],
            heading=_("Columns layout"),
        ),
        MultiFieldPanel(
            [FieldPanel("minimal_links")],
            heading=_("Minimal layout"),
        ),
        FieldPanel("copyright_text"),
    ]

    class Meta:
        verbose_name = _("Footer")


@register_setting(icon="globe", order=40)
class SocialSettings(BaseSiteSetting):
    """Settings > Social — social media links and display options."""

    social_links = StreamField(
        [("link", SocialLinkBlock())],
        blank=True,
        verbose_name=_("social links"),
        use_json_field=True,
    )
    show_in_header = models.BooleanField(
        default=False,
        verbose_name=_("show in header"),
        help_text=_("Display social media icons in the site header."),
    )
    show_in_footer = models.BooleanField(
        default=True,
        verbose_name=_("show in footer"),
        help_text=_("Display social media icons in the site footer."),
    )

    panels = [
        FieldPanel("social_links"),
        MultiFieldPanel(
            [FieldPanel("show_in_header"), FieldPanel("show_in_footer")],
            heading=_("Display options"),
        ),
    ]

    class Meta:
        verbose_name = _("Social")


class IntegrationsStreamBlock(StreamBlock):
    """
    The "Add new integration" list on Settings > Integrations.

    Named declarative StreamBlock subclass (rather than an inline tuple list)
    so fork sites can override individual integration config blocks the same
    way SectionContentBlock/BodyStreamBlock allow overriding individual
    content blocks (see AGENTS.md architecture rule #9). Each attribute name
    here must match the corresponding IntegrationType.slug registered in
    wtrx/integrations/registry.py.
    """

    actionkit = ActionKitConfigBlock()
    fundraiseup = FundraiseUpConfigBlock()
    actblue = ActBlueConfigBlock()
    action_network = ActionNetworkConfigBlock()

    class Meta:
        label = _("Integrations")


@register_setting(icon="cogs", order=50)
class IntegrationSettings(BaseSiteSetting):
    """
    Settings > Integrations — add and configure any number of pre-set integrations.

    Each entry in `integrations` is one enabled-or-disabled instance of a
    pre-set integration type (ActionKit, Fundraise Up, ActBlue, Action
    Network, ...). Multiple integrations — even multiple in the same
    category — can be enabled simultaneously; there is no single "active
    platform" choice. Block visibility in the page editor is driven by which
    integrations are enabled here (see wagtail_hooks.py).
    """

    integrations = StreamField(
        IntegrationsStreamBlock,
        blank=True,
        verbose_name=_("integrations"),
        help_text=_("Add and configure the platforms this site integrates with."),
        use_json_field=True,
    )

    panels = [
        FieldPanel("integrations"),
    ]

    def get_integration_config(self, slug):
        """
        Return the StructValue of the first *enabled* entry of this integration
        type, or None if it isn't configured or is disabled.
        """
        for block in self.integrations:
            if block.block_type == slug and block.value.get("enabled", True):
                return block.value
        return None

    def is_integration_enabled(self, slug):
        return self.get_integration_config(slug) is not None

    def enabled_slugs_by_category(self, category):
        """Return the slugs of all enabled integrations in the given category."""
        from .integrations.registry import get_integration

        slugs = []
        for block in self.integrations:
            if not block.value.get("enabled", True):
                continue
            integration_type = get_integration(block.block_type)
            if integration_type and integration_type.category == category:
                slugs.append(block.block_type)
        return slugs

    def get_action_network_api_key(self):
        """
        Return the effective Action Network API key.

        The env/Django setting wins over the DB value because API keys should
        not be stored in the database in production. Set
        WTRX_ACTION_NETWORK_API_KEY as an environment variable to override the
        DB-stored value.
        """
        env_key = getattr(settings, "WTRX_ACTION_NETWORK_API_KEY", "")
        if env_key:
            return env_key
        config = self.get_integration_config("action_network")
        return config.get("api_key", "") if config else ""

    def get_actionkit_api_password(self):
        """
        Return the effective ActionKit API password.

        Like get_action_network_api_key, the env/Django setting wins over the
        DB value because API secrets should not live in the database in
        production. Set WTRX_ACTIONKIT_API_PASSWORD as an environment variable
        to override.
        """
        env_password = getattr(settings, "WTRX_ACTIONKIT_API_PASSWORD", "")
        if env_password:
            return env_password
        config = self.get_integration_config("actionkit")
        return config.get("api_password", "") if config else ""

    def head_html(self):
        """
        Concatenate the head-injection markup for every enabled integration
        that declares a `head_html_field` (e.g. Fundraise Up's installation
        script). Rendered as-is in base.html's <head> — same trust level as
        editor-pasted vendor scripts elsewhere in this settings model.
        """
        fragments = []
        for integration_type in all_integrations():
            if not integration_type.head_html_field:
                continue
            config = self.get_integration_config(integration_type.slug)
            if config:
                fragments.append(config.get(integration_type.head_html_field, ""))
        return mark_safe("".join(fragments))

    class Meta:
        verbose_name = _("Integrations")


@register_setting(icon="link", order=60)
class AdminMenuSettings(BaseSiteSetting):
    """Settings > Admin menu — configures shortcut links in the Wagtail admin sidebar."""

    blog_index_page = models.ForeignKey(
        "wagtailcore.Page",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("blog index page"),
        help_text=_(
            "The page that lists your blog posts. When set, a 'Blog' shortcut "
            "appears in the admin sidebar linking to it. Leave blank to hide "
            "the shortcut."
        ),
    )

    panels = [
        FieldPanel("blog_index_page"),
    ]

    class Meta:
        verbose_name = _("Admin menu")

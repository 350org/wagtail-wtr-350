from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel, MultiFieldPanel, ObjectList, TabbedInterface
from wagtail.blocks import (
    BooleanBlock,
    CharBlock,
    ChoiceBlock,
    PageChooserBlock,
    StreamBlock,
    StructBlock,
    StructBlockValidationError,
    URLBlock,
)
from wagtail.contrib.settings.models import BaseSiteSetting, register_setting
from wagtail.fields import StreamField
from wagtail_ai.panels import AIDescriptionFieldPanel, AIFieldPanel

from .images import CustomImage
from .integrations.actblue import (
    ActBlueConfigBlock,
    validate_comma_separated_amounts,  # noqa: F401 -- referenced by historical migration 0001_initial
)
from .integrations.action_network import ActionNetworkConfigBlock
from .integrations.actionkit import ActionKitConfigBlock
from .integrations.fundraiseup import FundraiseUpConfigBlock
from .integrations.gtm import GoogleTagManagerConfigBlock
from .integrations.registry import all_integrations, get_integration
from .integrations.wagtail_forms import WagtailFormsConfigBlock
from .validators import validate_balanced_html


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


def _primary_navigation_blocks():
    """
    Link block choices shared between the default primary navigation
    (NavigationSettings.primary_navigation) and each per-root-page override's
    own navigation (NavigationOverrideBlock.primary_navigation). Returns a
    fresh list of block instances each call since block instances aren't
    safe to reuse across separate parent block definitions.
    """
    return [
        ("internal", InternalLinkBlock()),
        ("external", ExternalLinkBlock()),
        ("anchor", AnchorLinkBlock()),
        ("submenu", SubmenuBlock()),
    ]


class NavigationOverrideBlock(StructBlock):
    """
    An alternate navigation (links, CTA button, layout) scoped to a root page
    and everything beneath it. See NavigationSettings.resolved_for_page().
    """

    root_page = PageChooserBlock(
        label=_("Root page"),
        help_text=_(
            "This page and every page beneath it will use this navigation "
            "instead of the default. If a page falls under more than one "
            "override, the override with the most specific (closest) root "
            "page wins."
        ),
    )
    regional_label = CharBlock(
        required=False,
        max_length=50,
        label=_("Regional label"),
        help_text=_(
            "Region name shown as a badge beside the logo for this section, "
            "e.g. \"Canada\". Leave blank for no badge."
        ),
    )
    primary_navigation = StreamBlock(
        _primary_navigation_blocks(),
        blank=True,
        label=_("Primary navigation"),
        help_text=_("Links shown in the main navigation bar for this section."),
    )
    cta_text = CharBlock(required=False, label=_("CTA button text"))
    cta_page = PageChooserBlock(
        required=False,
        label=_("CTA page"),
        help_text=_(
            "Internal link for the CTA button. Set either this, CTA URL, or "
            "CTA anchor, not more than one."
        ),
    )
    cta_url = URLBlock(
        required=False,
        label=_("CTA URL"),
        help_text=_(
            "External link for the CTA button. Set either this, CTA page, or "
            "CTA anchor, not more than one."
        ),
    )
    cta_anchor = CharBlock(
        required=False,
        label=_("CTA anchor"),
        help_text=_(
            "Anchor link for the CTA button (without the # symbol, e.g. "
            "'donate'). Set this instead of CTA page or CTA URL to link to an "
            "anchor on the current page."
        ),
    )
    collapse_desktop_menu = BooleanBlock(
        required=False,
        label=_("Collapse desktop menu"),
        help_text=_(
            "Always show the hamburger menu icon, even on desktop, for this "
            "section."
        ),
    )

    def clean(self, value):
        cleaned = super().clean(value)
        errors = {}
        cta_page = cleaned.get("cta_page")
        cta_url = cleaned.get("cta_url")
        cta_anchor = cleaned.get("cta_anchor")
        cta_targets_set = sum([bool(cta_page), bool(cta_url), bool(cta_anchor)])
        if cleaned.get("cta_text") and cta_targets_set == 0:
            msg = ValidationError(
                _(
                    "Set either a CTA page, CTA URL, or CTA anchor when CTA "
                    "button text is provided."
                )
            )
            errors["cta_page"] = msg
            errors["cta_url"] = msg
            errors["cta_anchor"] = msg
        if cta_targets_set > 1:
            msg = ValidationError(
                _("Set only one of CTA page, CTA URL, or CTA anchor — not multiple.")
            )
            errors["cta_url"] = msg
            errors["cta_anchor"] = msg
        if cta_targets_set > 0 and not cleaned.get("cta_text"):
            errors["cta_text"] = ValidationError(
                _("CTA button text is required when a CTA page, URL, or anchor is set.")
            )
        if errors:
            raise StructBlockValidationError(block_errors=errors)
        return cleaned

    class Meta:
        icon = "site"
        label = _("Navigation override")


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


# Module-level per AGENTS.md pitfall #10 — gettext_lazy in choices requires
# module-level definition to avoid migration serialization failures.
FOOTER_LAYOUT_CHOICES = [
    ("columns", _("Columns")),
    ("minimal", _("Minimal")),
]


class FooterOverrideBlock(StructBlock):
    """
    An alternate footer (layout, columns/links, copyright) scoped to a root
    page and everything beneath it. See FooterSettings.resolved_for_page().
    """

    root_page = PageChooserBlock(
        label=_("Root page"),
        help_text=_(
            "This page and every page beneath it will use this footer "
            "instead of the default. If a page falls under more than one "
            "override, the override with the most specific (closest) root "
            "page wins."
        ),
    )
    regional_label = CharBlock(
        required=False,
        max_length=50,
        label=_("Regional label"),
        help_text=_(
            "Region name shown as a badge beside the logo for this section, "
            "e.g. \"Canada\". Leave blank for no badge."
        ),
    )
    layout = ChoiceBlock(
        choices=FOOTER_LAYOUT_CHOICES,
        required=False,
        label=_("Footer layout"),
        help_text=_("Leave blank to use the columns layout."),
    )
    footer_navigation = StreamBlock(
        [("column", FooterColumnBlock())],
        blank=True,
        label=_("Footer navigation"),
        help_text=_(
            "Footer link columns for this section. Each column has a "
            "heading and a list of links."
        ),
    )
    minimal_links = StreamBlock(
        [
            ("internal", InternalLinkBlock()),
            ("external", ExternalLinkBlock()),
            ("anchor", AnchorLinkBlock()),
        ],
        blank=True,
        label=_("Minimal footer links"),
        help_text=_(
            "Flat list of links displayed inline in the minimal footer "
            "layout for this section."
        ),
    )
    copyright_text = CharBlock(
        required=False,
        max_length=255,
        label=_("Copyright text"),
        help_text=_(
            'Optional. Overrides the default "© {year} {site name}" '
            "copyright line for this section."
        ),
    )
    newsletter_actionkit_shortname = CharBlock(
        required=False,
        label=_("Newsletter signup — ActionKit page shortname"),
        help_text=_(
            "The ActionKit page's short name (e.g. 'newsletter-canada') "
            "powering this section's footer signup box. Leave blank to show "
            "no signup box for this section, even if the site default has "
            "one set."
        ),
    )
    newsletter_success_message = CharBlock(
        required=False,
        label=_("Newsletter signup — success message"),
        help_text=_(
            "Shown in place of the form after a successful signup for this "
            "section. Falls back to the site default's message when left "
            "blank (unlike the other fields on this override, which show "
            "nothing rather than fall back)."
        ),
    )

    class Meta:
        icon = "bars"
        label = _("Footer override")


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
    ("whatsapp", "WhatsApp"),
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


class RegionalSiteLinkBlock(StructBlock):
    """
    A single entry in the "Around the World" region switcher — a link out to
    another regional 350.org site. Explicitly named (not anonymous) per the
    same migration-serialization rule as SocialLinkBlock.
    """

    text = CharBlock(label=_("Region name"), help_text=_('e.g. "Canada".'))
    description = CharBlock(
        required=False,
        max_length=255,
        label=_("Description"),
        help_text=_(
            "Optional. Shown as a subheading below the region name — for a "
            "linked site that isn't a regional site itself and needs a "
            "line of context (e.g. \"350 Action\", \"350 Global\"). Entries "
            "with a description render in their own two-column row below "
            "the plain region links, since the extra text needs more room."
        ),
    )
    url = URLBlock(label=_("URL"), help_text=_("Link to that region's site."))

    class Meta:
        icon = "site"
        label = _("Regional site link")


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
            [
                FieldPanel("default_meta_image"),
                AIDescriptionFieldPanel("site_description"),
            ],
            heading=_("SEO defaults"),
        ),
    ]

    class Meta:
        verbose_name = _("Branding & SEO")


@register_setting(icon="list-ul", order=20)
class NavigationSettings(BaseSiteSetting):
    """Settings > Navigation — primary nav links, CTA button, layout options."""

    primary_navigation = StreamField(
        _primary_navigation_blocks(),
        blank=True,
        verbose_name=_("Primary navigation"),
        help_text=_("Links shown in the main navigation bar."),
        use_json_field=True,
    )
    regional_label = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("regional label"),
        help_text=_(
            "Region name shown as a badge beside the logo across the whole "
            "site, e.g. \"Canada\". Leave blank for no badge. Sections with "
            "their own navigation override set this on the override instead."
        ),
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
        verbose_name=_("Collapse desktop menu"),
        help_text=_(
            "Always show the hamburger menu icon, even on desktop. "
            "Navigation links are hidden behind the menu toggle at all screen sizes."
        ),
    )
    navigation_overrides = StreamField(
        [("override", NavigationOverrideBlock())],
        blank=True,
        verbose_name=_("navigation overrides"),
        help_text=_(
            "Alternate navigations for specific sections of the site. Each "
            "override applies to a chosen root page and every page beneath "
            "it; pages outside any override use the default navigation "
            "above."
        ),
        use_json_field=True,
    )

    main_panels = [
        FieldPanel("primary_navigation"),
        FieldPanel("regional_label"),
        MultiFieldPanel(
            [
                AIFieldPanel("cta_text"),
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
    advanced_panels = [
        FieldPanel("navigation_overrides"),
    ]
    # Wagtail's settings edit view checks for an `edit_handler` attribute
    # before falling back to auto-building one from `panels` (see
    # wagtail.contrib.settings.views.get_setting_edit_handler) — same
    # TabbedInterface([ObjectList(...), ...]) pattern every page model in
    # wtrx/models.py already uses for its own edit_handler. `panels` is
    # kept as the flat main_panels + advanced_panels list too, matching
    # every other settings model in this file, even though edit_handler is
    # what actually renders the form now.
    panels = main_panels + advanced_panels
    edit_handler = TabbedInterface(
        [
            ObjectList(main_panels, heading=_("Main")),
            ObjectList(advanced_panels, heading=_("Overrides")),
        ]
    )

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

    @property
    def root_page(self):
        """
        Always ``None`` for the site default. Present so templates can read
        ``nav.root_page`` off whatever ``resolved_for_page()`` handed them —
        a NavigationOverrideBlock StructValue has a real root page, the site
        default has none (its logo lockup links to ``/``).
        """
        return None

    def resolved_for_page(self, page):
        """
        Return the navigation to render for ``page``: either this settings
        instance itself (the site default) or the value of the most specific
        matching entry in ``navigation_overrides`` — whichever's ``root_page``
        is an ancestor of (or is) ``page``, breaking ties by depth so a more
        specific/nested override wins over a broader one.

        The returned object exposes the same attribute names either way
        (``primary_navigation``, ``regional_label``, ``root_page``,
        ``cta_text``, ``cta_page``, ``cta_url``, ``cta_anchor``,
        ``collapse_desktop_menu``), so templates don't need to care which one
        they got. ``root_page`` only exists on an override — the ``root_page``
        property below supplies the ``None`` the site default would otherwise
        be missing.
        """
        if page is None:
            return self
        best_override = None
        best_depth = -1
        for stream_child in self.navigation_overrides:
            override = stream_child.value
            root_page = override.get("root_page")
            if root_page is None:
                continue
            if page.path.startswith(root_page.path) and root_page.depth > best_depth:
                best_override = override
                best_depth = root_page.depth
        return best_override if best_override is not None else self

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
    regional_label = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("regional label"),
        help_text=_(
            "Region name shown as a badge beside the logo across the whole "
            "site, e.g. \"Canada\". Leave blank for no badge. Sections with "
            "their own footer override set this on the override instead."
        ),
    )
    footer_overrides = StreamField(
        [("override", FooterOverrideBlock())],
        blank=True,
        verbose_name=_("footer overrides"),
        help_text=_(
            "Alternate footers for specific sections of the site. Each "
            "override applies to a chosen root page and every page beneath "
            "it; pages outside any override use the default footer above."
        ),
        use_json_field=True,
    )
    regional_sites = StreamField(
        [("site", RegionalSiteLinkBlock())],
        blank=True,
        verbose_name=_("regional sites"),
        help_text=_(
            'Links to other regional 350.org sites, shown in an "Around the '
            "World\" dropdown beside the footer logo on every page — the "
            "same list regardless of any footer override, since it isn't "
            "region-specific content itself."
        ),
        use_json_field=True,
    )
    newsletter_actionkit_shortname = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("newsletter signup — ActionKit page shortname"),
        help_text=_(
            "The ActionKit page's short name (e.g. 'newsletter') powering "
            "the site-wide footer signup box. Its form is fetched from "
            "ActionKit and rendered automatically, the same as the "
            "Sign Up (ActionKit) block. Leave blank to show no signup box. "
            "Sections with their own footer override set this on the "
            "override instead."
        ),
    )
    newsletter_success_message = models.CharField(
        max_length=255,
        blank=True,
        default=_("Thanks for signing up!"),
        verbose_name=_("newsletter signup — success message"),
        help_text=_(
            "Shown in place of the form after a successful newsletter "
            "signup. Sections with their own footer override set this on "
            "the override instead."
        ),
    )

    main_panels = [
        FieldPanel("layout"),
        MultiFieldPanel(
            [FieldPanel("footer_navigation")],
            heading=_("Columns layout"),
        ),
        MultiFieldPanel(
            [FieldPanel("minimal_links")],
            heading=_("Minimal layout"),
        ),
        AIFieldPanel("copyright_text"),
        FieldPanel("regional_label"),
        FieldPanel("newsletter_actionkit_shortname"),
        FieldPanel("newsletter_success_message"),
    ]
    advanced_panels = [
        FieldPanel("footer_overrides"),
        FieldPanel("regional_sites"),
    ]
    # See NavigationSettings for why both a flat `panels` and a
    # TabbedInterface `edit_handler` are defined here.
    panels = main_panels + advanced_panels
    edit_handler = TabbedInterface(
        [
            ObjectList(main_panels, heading=_("Main")),
            ObjectList(advanced_panels, heading=_("Overrides")),
        ]
    )

    @property
    def root_page(self):
        """
        Always ``None`` for the site default. Present so templates can read
        ``footer.root_page`` off whatever ``resolved_for_page()`` handed
        them — see NavigationSettings.root_page, same trick.
        """
        return None

    def resolved_for_page(self, page):
        """
        Return the footer to render for ``page``: either this settings
        instance itself (the site default) or the value of the most
        specific matching entry in ``footer_overrides`` — whichever's
        ``root_page`` is an ancestor of (or is) ``page``, breaking ties by
        depth so a more specific/nested override wins over a broader one.

        See NavigationSettings.resolved_for_page() — identical algorithm.
        The returned object exposes the same attribute names either way
        (``layout``, ``footer_navigation``, ``minimal_links``,
        ``copyright_text``, ``regional_label``, ``root_page``).
        """
        if page is None:
            return self
        best_override = None
        best_depth = -1
        for stream_child in self.footer_overrides:
            override = stream_child.value
            root_page = override.get("root_page")
            if root_page is None:
                continue
            if page.path.startswith(root_page.path) and root_page.depth > best_depth:
                best_override = override
                best_depth = root_page.depth
        return best_override if best_override is not None else self

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

    @property
    def twitter_handle(self):
        """
        Derive an "@handle" for the twitter:site meta tag (base.html) from
        this site's "twitter" entry in social_links, if any — e.g.
        "https://twitter.com/350" or "https://x.com/350" both yield "@350".

        Replaces the old separate BrandingSEOSettings.twitter_site field
        (see the data migration that removed it): that field and a
        "twitter" entry here both claimed to be the site's Twitter/X
        presence, with nothing keeping them in sync. One source of truth
        now — an editor sets the profile URL here once, for both the
        header/footer icon and this meta tag.
        """
        from urllib.parse import urlparse

        for block in self.social_links:
            if block.value.get("platform") != "twitter":
                continue
            path = urlparse(block.value.get("url", "")).path.strip("/")
            handle = path.split("/")[0] if path else ""
            if handle:
                return f"@{handle}"
        return ""

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
    wagtail_forms = WagtailFormsConfigBlock()
    google_tag_manager = GoogleTagManagerConfigBlock()

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
    custom_head_html = models.TextField(
        blank=True,
        validators=[validate_balanced_html],
        verbose_name=_("custom head code"),
        help_text=_(
            "Optional. Raw HTML/script markup inserted verbatim near the top "
            "of every page's <head> — for one-off scripts that don't warrant "
            "their own integration above. Rendered exactly as given, after "
            "every enabled integration's own head markup; only use this for "
            "code you trust."
        ),
    )
    custom_body_html = models.TextField(
        blank=True,
        validators=[validate_balanced_html],
        verbose_name=_("custom body code"),
        help_text=_(
            "Optional. Raw HTML/script markup inserted verbatim immediately "
            "after <body> opens on every page — for markup that specifically "
            "has to run early in the body (e.g. a <noscript> fallback). "
            "Rendered exactly as given, after every enabled integration's "
            "own body markup; only use this for code you trust."
        ),
    )

    panels = [
        FieldPanel("integrations"),
        MultiFieldPanel(
            [
                FieldPanel("custom_head_html"),
                FieldPanel("custom_body_html"),
            ],
            heading=_("Custom code"),
        ),
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

    def _explicit_entry_enabled(self, slug):
        """
        Return the `enabled` value of this slug's own entry in
        `integrations`, or None if no entry exists at all.

        Split out of is_integration_enabled() so the category-yielding check
        below can ask "did an editor explicitly turn this sibling on"
        without going through that sibling's own default_enabled fallback —
        calling is_integration_enabled() recursively there would be fine
        today (only one slug has default_enabled=True) but would risk
        infinite recursion the day a second one does, since each would ask
        the other to resolve its own default first.
        """
        for block in self.integrations:
            if block.block_type == slug:
                return bool(block.value.get("enabled", True))
        return None

    def is_integration_enabled(self, slug):
        """
        Return whether this integration/feature should be treated as active.

        An explicit entry in `integrations` always wins, in either direction:
        if one exists for this slug, its own `enabled` value is the answer,
        regardless of the registry default or the category-yielding rule
        below. Only when there's no entry at all do we fall back to
        IntegrationType.default_enabled — True for a built-in,
        zero-configuration feature like Wagtail Forms (which should read as
        "on" until a site explicitly disables it), False for every genuine
        third-party integration (which should stay hidden until a site
        explicitly configures and enables it). See
        IntegrationType.default_enabled for the full rationale.

        A default_enabled=True slug (a built-in, zero-configuration option
        like Wagtail Forms) with no entry of its own additionally yields to
        any *genuine third-party* integration in the same category that has
        been explicitly enabled: turning on ActionKit or Action Network
        (both category="signup") hides Wagtail Forms by default, on the
        assumption a site that has wired up a real signup integration
        doesn't also want the built-in option cluttering the "Add block"
        picker. Add an explicit entry for the built-in block itself
        (enabled or not) to override this either way.

        Only a sibling with its own default_enabled=False can trigger this
        — two built-in, default_enabled=True options in the same category
        would never yield to each other, even given a redundant explicit
        "enabled=True" entry on one of them (there's only one such slug
        today, Wagtail Forms, but this guards against the surprising
        side effect a second one would otherwise create: an editor
        re-confirming one built-in as enabled — which changes nothing under
        its own default — silently hiding the other).
        """
        explicit = self._explicit_entry_enabled(slug)
        if explicit is not None:
            return explicit

        integration_type = get_integration(slug)
        if not integration_type or not integration_type.default_enabled:
            return False

        for other in all_integrations():
            if other.slug == slug or other.category != integration_type.category:
                continue
            if other.default_enabled:
                continue
            if self._explicit_entry_enabled(other.slug):
                return False

        return True

    def enabled_slugs_by_category(self, category):
        """Return the slugs of all enabled integrations in the given category."""
        return [
            integration_type.slug
            for integration_type in all_integrations()
            if integration_type.category == category
            and self.is_integration_enabled(integration_type.slug)
        ]

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
        script, Google Tag Manager's own head snippet), followed by
        `custom_head_html` — the site-wide fallback for a one-off script
        that doesn't warrant its own integration module. Rendered as-is in
        base.html's <head> — same trust level as editor-pasted vendor
        scripts elsewhere in this settings model.
        """
        fragments = []
        for integration_type in all_integrations():
            if not integration_type.head_html_field:
                continue
            config = self.get_integration_config(integration_type.slug)
            if config:
                fragments.append(config.get(integration_type.head_html_field, ""))
        if self.custom_head_html:
            fragments.append(self.custom_head_html)
        return mark_safe("".join(fragments))

    def body_html(self):
        """
        Same as head_html() but for `body_html_field`/`custom_body_html` —
        markup rendered verbatim immediately after <body> opens (base.html)
        instead of in <head>. Google Tag Manager's <noscript> fallback
        iframe (wtrx/integrations/gtm.py) is the first integration to
        actually use body_html_field; custom_body_html covers anything else
        that specifically needs to run this early in the body rather than
        in <head>.
        """
        fragments = []
        for integration_type in all_integrations():
            if not integration_type.body_html_field:
                continue
            config = self.get_integration_config(integration_type.slug)
            if config:
                fragments.append(config.get(integration_type.body_html_field, ""))
        if self.custom_body_html:
            fragments.append(self.custom_body_html)
        return mark_safe("".join(fragments))

    class Meta:
        verbose_name = _("Integrations")


class AdminSidebarShortcutBlock(StructBlock):
    """
    A single shortcut link in the Wagtail admin sidebar, opening the given
    page's page-explorer view. Generalizes what used to be two hardcoded
    fields (blog_index_page, press_releases_index_page) on AdminMenuSettings,
    each with its own hand-written MenuItem subclass and hook in
    wagtail_hooks.py — see add_admin_menu_shortcuts() there, which now
    builds one MenuItem per entry in this list instead.
    """

    label = CharBlock(
        required=False,
        label=_("Label"),
        help_text=_("Shown in the sidebar. Leave blank to use the page's own title."),
    )
    page = PageChooserBlock(
        label=_("Page"),
        help_text=_(
            "The shortcut opens this page's listing in the page explorer. "
            "Hidden automatically if the page is unpublished."
        ),
    )
    icon = CharBlock(
        required=False,
        max_length=50,
        label=_("Icon"),
        help_text=_(
            "Optional. A Wagtail admin icon name, e.g. 'doc-empty' or "
            "'clipboard-list' — see Wagtail's icon reference "
            "(https://docs.wagtail.org/en/stable/advanced_topics/icons.html). "
            "Leave blank for a generic document icon."
        ),
    )

    class Meta:
        icon = "link"
        label = _("Sidebar shortcut")


@register_setting(icon="link", order=60)
class AdminMenuSettings(BaseSiteSetting):
    """Settings > Admin menu — configures shortcut links in the Wagtail admin sidebar."""

    sidebar_shortcuts = StreamField(
        [("shortcut", AdminSidebarShortcutBlock())],
        blank=True,
        verbose_name=_("sidebar shortcuts"),
        help_text=_(
            "Shortcut links shown in the Wagtail admin sidebar, each opening "
            "a chosen page's listing in the page explorer — e.g. quick "
            "access to your blog or press releases index. Add as many as "
            "you like."
        ),
        use_json_field=True,
    )

    panels = [
        FieldPanel("sidebar_shortcuts"),
    ]

    class Meta:
        verbose_name = _("Admin menu")

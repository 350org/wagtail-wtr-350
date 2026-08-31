import logging

from django import forms
from django.conf import settings
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models
from django.http import JsonResponse
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from wagtail.admin.forms import WagtailAdminPageForm
from wagtail.admin.panels import (
    FieldPanel,
    InlinePanel,
    MultiFieldPanel,
    ObjectList,
    TabbedInterface,
)
from wagtail.blocks import StreamValue, StructValue
from wagtail.blocks.list_block import ListValue
from wagtail.contrib.forms.models import AbstractEmailForm, AbstractFormField
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Page
from wagtail.snippets.models import register_snippet
from wagtail_ai.panels import AIDescriptionFieldPanel, AITitleFieldPanel
from wagtailmedia.edit_handlers import MediaChooserPanel

from .blocks import BACKGROUND_COLOR_CHOICES, BodyStreamBlock, HeroCTABlock
from .constants import RICHTEXT_FEATURES_HERO, RICHTEXT_FEATURES_INLINE
from .images import CustomImage, CustomRendition  # noqa: F401 — register with Django ORM
from .integrations import actionkit
from .site_settings import (  # noqa: F401 — register with Django ORM
    BrandingSEOSettings,
    FooterSettings,
    IntegrationSettings,
    NavigationSettings,
    SocialSettings,
)

logger = logging.getLogger(__name__)


class BasePage(Page):
    """
    Abstract base page for all page types in this project.

    Adds:
    - meta_image: optional OG/Twitter image override
    - hide_from_search: exclude from Wagtail search results and sitemap

    All project page models should inherit from BasePage rather than Page directly.
    """

    meta_image = models.ForeignKey(
        CustomImage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("meta image"),
        help_text=_(
            "Optional. Overrides the default meta image for social sharing. "
            "Falls back to Branding & SEO settings default."
        ),
    )
    hide_from_search = models.BooleanField(
        default=False,
        verbose_name=_("hide from search"),
        help_text=_("Exclude this page from search results and the sitemap."),
    )
    canonical_url = models.URLField(
        blank=True,
        verbose_name=_("canonical URL"),
        help_text=_(
            "Optional. Set if this page's content is duplicated elsewhere "
            "and search engines should treat another URL as the primary "
            "version. Defaults to this page's own URL."
        ),
    )

    # AI-assisted title panel, reused by every concrete page model below in
    # place of Page.content_panels (which is just [TitleFieldPanel("title")])
    # — swaps in wagtail-ai's drop-in replacement so the title field gets an
    # AI-assist button in the admin.
    title_panels = [AITitleFieldPanel("title")]

    promote_panels = [
        # Rebuilt by hand (not Page.promote_panels[0]) because
        # AIDescriptionFieldPanel needs to replace one nested field
        # (search_description) inside it — accepted tradeoff: if a future
        # Wagtail release adds a new field to its own default "For search
        # engines" panel, it won't automatically appear here too.
        MultiFieldPanel(
            [
                FieldPanel("slug"),
                FieldPanel("seo_title"),
                # AI-assisted meta description, in place of Page.promote_panels'
                # plain FieldPanel("search_description").
                AIDescriptionFieldPanel("search_description"),
            ],
            heading=_("For search engines"),
        ),
        # "For site menus" is intentionally omitted — this project doesn't
        # use Wagtail's automatic page-tree menu APIs (navigation is driven
        # entirely by NavigationSettings, a hand-curated StreamField), so
        # editors never need to see the show_in_menus checkbox. The field
        # itself is untouched (Wagtail core still reads/writes it, default
        # False), only the editor UI panel is dropped.
        MultiFieldPanel(
            [
                FieldPanel("meta_image"),
                FieldPanel("hide_from_search"),
                FieldPanel("canonical_url"),
            ],
            heading=_("SEO"),
        ),
    ]

    # Page.settings_panels (scheduled "go live"/"expire" dates, and
    # internal commenting) — inherited automatically, but every concrete
    # page model below defines its own edit_handler as a TabbedInterface of
    # explicit ObjectLists, which does NOT pull in settings_panels the way
    # Wagtail's own default single-ObjectList edit_handler would. Named here
    # (matching the title_panels/promote_panels pattern above) so it's
    # obvious every concrete model must include
    # ObjectList(settings_panels, heading=_("Settings")) as a third tab —
    # omit it and the whole Settings tab, including comments, silently
    # disappears with no error.
    settings_panels = Page.settings_panels

    def get_context(self, request, *args, **kwargs):
        ctx = super().get_context(request, *args, **kwargs)
        # Ensure transparent_header is always present in context so header.html
        # never relies on implicit falsy-absent behaviour. setdefault is used
        # intentionally: HomePage.get_context() calls super() first and then
        # sets ctx["transparent_header"] = self.use_transparent_header, so this
        # default is only applied for non-home pages where the key is absent.
        ctx.setdefault("transparent_header", False)
        return ctx

    def get_sitemap_urls(self, request=None):
        if self.hide_from_search:
            return []
        return super().get_sitemap_urls(request)

    class Meta:
        abstract = True


class HeroMixin(models.Model):
    """
    Mixin adding a hero section to any page type.

    Renders as one of two variants (see components/hero.html): "full" — the
    original full-viewport hero, background image or video, left-aligned
    text anchored toward the bottom, optional cta — or "banner" — a compact
    rounded panel, solid/gradient color background (reusing CalloutBlock's
    5-color system) beside an image, no cta. Which variant a page gets is
    fixed per page type via the hero_variant class attribute, not
    editor-controlled: HomePage overrides it to "full"; every other
    HeroMixin page type (ContentPage, IndexPage, Blogs) uses the "banner"
    default.

    Fields:
    - hero_headline: optional override for the page title as the displayed h1
    - hero_copy: optional subtext below the headline
    - hero_image: optional background/feature image. "full" variant: also
      used as the video poster fallback, and as the background itself when
      no video is set. "banner" variant: the image beside the color panel.
    - hero_video: optional background video (autoplay/muted/loop), with a
      custom pause/play toggle in the corner. Takes over from hero_image as
      the background/image area on both variants; hero_image is still used
      as the poster fallback if the video has none.
    - hero_banner_color: background color/gradient. "banner" variant only —
      "full" never shows a solid color background.
    - hero_cta: optional signup/donate/announcement widget (HeroCTABlock, at
      most one). "full" variant renders whichever choice is set; "banner"
      variant only renders the plain `button` choice (see
      components/hero.html), silently skipping signup/donate/announcement.

    There used to be an editable hero_layout field (centered vs. left-
    aligned text, "full" variant only) — removed in favor of a single fixed
    layout (left-aligned, matching what every real "full"-variant page
    already used in practice: Home and every regional homepage). See
    components/hero.html — it no longer branches on layout at all.

    hero_video only matters for the "full" variant, so a "banner"-only page
    type should use banner_hero_panels (defined below, next to hero_panels)
    instead of hero_panels — it exposes headline/copy/image/banner_color
    plus hero_cta (restricted in practice to its `button` choice, per
    above), the fields "banner" actually renders. hero_video stays a real
    model field on every HeroMixin subclass (including "banner"-only ones)
    rather than being split into a separate mixin, so this is a panel-only
    choice with no schema difference between page types — see
    banner_hero_panels' own docstring for why.

    Use: include `components/hero.html` in the page template.
    """

    hero_variant = "banner"

    hero_headline = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("hero headline"),
        help_text=_(
            "Optional. Overrides the page title as the displayed heading. "
            "Leave blank to use the page title."
        ),
    )
    hero_copy = RichTextField(
        blank=True,
        features=RICHTEXT_FEATURES_HERO,
        verbose_name=_("hero copy"),
        help_text=_("Optional subtext displayed below the headline."),
    )
    hero_image = models.ForeignKey(
        CustomImage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("hero image"),
        help_text=_(
            "Optional hero background or feature image. Also used as the video poster if no thumbnail is set on the video."
        ),
    )
    hero_video = models.ForeignKey(
        "wagtailmedia.Media",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        limit_choices_to={"type": "video"},
        verbose_name=_("hero video"),
        help_text=_(
            "Optional. When set, this video autoplays (muted, looping) as the "
            "hero's full-bleed background instead of the hero image, with a "
            "pause/play button in the corner. "
            "Upload a thumbnail on the video in the media library to use as a poster frame; "
            "falls back to the hero image above if no thumbnail is set."
        ),
    )
    hero_banner_color = models.CharField(
        max_length=20,
        choices=BACKGROUND_COLOR_CHOICES,
        default="navy",
        verbose_name=_("hero banner color"),
        help_text=_(
            "Background color for the compact hero banner. Only affects pages whose "
            "hero renders as a banner (i.e. every page except the homepage)."
        ),
    )
    hero_cta = StreamField(
        HeroCTABlock(),
        blank=True,
        verbose_name=_("hero call to action"),
        help_text=_(
            "Optional signup bar, donate block, or announcement bar shown "
            "below the hero copy. At most one."
        ),
        use_json_field=True,
    )

    hero_panels = [
        MultiFieldPanel(
            [
                FieldPanel("hero_headline"),
                FieldPanel("hero_copy"),
                FieldPanel("hero_image"),
                MediaChooserPanel("hero_video", media_type="video"),
                FieldPanel("hero_banner_color"),
                FieldPanel("hero_cta"),
            ],
            heading=_("Hero"),
        ),
    ]

    # Panel-only subset for HeroMixin page types that never leave the
    # "banner" variant (ContentPage, IndexPage, Blogs — every HeroMixin page
    # except HomePage). hero_video stays a real model field (so no
    # migration, and no risk to any content already saved on existing
    # pages) but sits inert on "banner" per this class's own docstring, so
    # offering it as an editable option is misleading rather than merely
    # unused.
    #
    # hero_cta IS included here, unlike hero_video — components/hero.html's
    # "banner" variant rendering already only ever renders the plain
    # `button` choice from a hero_cta StreamField value (the signup/donate/
    # announcement choices are silently skipped there; see the comment
    # above that `{% for cta_block in hero.cta %}` loop), so a banner-hero
    # page editor adding a Button gets a real, working back/CTA link, not a
    # dead field.
    banner_hero_panels = [
        MultiFieldPanel(
            [
                FieldPanel("hero_headline"),
                FieldPanel("hero_copy"),
                FieldPanel("hero_image"),
                FieldPanel("hero_banner_color"),
                FieldPanel("hero_cta"),
            ],
            heading=_("Hero"),
        ),
    ]

    def get_hero_context(self):
        """
        Build the context dict consumed by components/hero.html. Same shape
        as HeroBlock.get_context()'s "hero" key so the template works
        identically for pages and StreamField hero blocks.

        copy_is_block=False because hero_copy is a RichTextField (string),
        not a StreamField block value — the template renders it with |richtext.
        """
        return {
            "variant": self.hero_variant,
            "headline": self.hero_headline or self.title,
            "copy": self.hero_copy,
            "copy_is_block": False,
            "image": self.hero_image,
            "video": self.hero_video,
            "banner_color": self.hero_banner_color,
            "cta": self.hero_cta,
        }

    class Meta:
        abstract = True


class PublishedDateMixin(models.Model):
    """
    Adds an editable "published at" date, independent of Wagtail's own
    first_published_at.

    Wagtail already tracks first_published_at automatically, but it's not
    editable and doesn't survive a page being unpublished/republished the
    way editors expect a display date to (e.g. backdating a post, or fixing
    a typo weeks later without it looking freshly published). Blog posts
    and press releases both need editors to control this directly, so it's
    a real field rather than reusing first_published_at — see
    PageCardsBlock.get_context(), which prefers this field when present.
    """

    published_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("published at"),
        help_text=_("The date shown on this page and used to order listings."),
    )

    published_date_panels = [
        FieldPanel("published_at"),
    ]

    class Meta:
        abstract = True


class BannerHeroMixin(models.Model):
    """
    A small header for page types that always render hero.html's "banner"
    variant and don't need HeroMixin's video/cta options — currently
    just Post. See HeroMixin for the full page-hero field set used by
    HomePage, and hero.html for the "banner" variant itself (same
    rendering, same 5-color system).

    Deliberately not built on top of HeroMixin: unlike ContentPage/IndexPage/
    Blogs (which already have HeroMixin's hero_video and hero_cta columns
    from before HeroMixin.banner_hero_panels existed, and keep them —
    unused — to avoid a schema change), Post has never had those columns at
    all. Per product decision a blog post's header shouldn't offer them as
    editable options, so there's no reason for Post to carry the unused
    database columns HeroMixin would add.
    """

    hero_headline = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("headline"),
        help_text=_(
            "Optional. Overrides the page title as the displayed heading. "
            "Leave blank to use the page title."
        ),
    )
    hero_copy = RichTextField(
        blank=True,
        features=RICHTEXT_FEATURES_HERO,
        verbose_name=_("copy"),
        help_text=_("Optional subtext displayed below the headline."),
    )
    hero_image = models.ForeignKey(
        CustomImage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("image"),
    )
    hero_banner_color = models.CharField(
        max_length=20,
        choices=BACKGROUND_COLOR_CHOICES,
        default="navy",
        verbose_name=_("banner color"),
    )

    banner_hero_panels = [
        MultiFieldPanel(
            [
                FieldPanel("hero_headline"),
                FieldPanel("hero_copy"),
                FieldPanel("hero_image"),
                FieldPanel("hero_banner_color"),
            ],
            heading=_("Header"),
        ),
    ]

    def get_banner_hero_context(self, **extra):
        """
        Build the "hero" context dict components/hero.html expects, forced
        to the "banner" variant. **extra lets a subclass merge in fields
        hero.html doesn't otherwise know about but the "banner" variant
        renders anyway when present — Post uses this for author/
        published_at.
        """
        context = {
            "variant": "banner",
            "headline": self.hero_headline or self.title,
            "copy": self.hero_copy,
            "copy_is_block": False,
            "image": self.hero_image,
            "video": None,
            "banner_color": self.hero_banner_color,
            "cta": [],
        }
        context.update(extra)
        return context

    class Meta:
        abstract = True


@register_snippet
class BlogCategory(models.Model):
    """
    Editor-managed taxonomy for Post.categories — a Snippet (rather
    than freeform tagging via the already-installed-but-unused `taggit`
    app) since categories here are meant to be a curated, admin-managed
    list, not something any author invents ad hoc per post. Snippets get
    their own list/create/edit/delete admin screens for free.
    """

    name = models.CharField(max_length=100, unique=True, verbose_name=_("name"))
    slug = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name=_("slug"),
        help_text=_("Used in the blog's category filter URL. Auto-filled from the name if left blank."),
        blank=True,
    )

    panels = [
        FieldPanel("name"),
        FieldPanel("slug"),
    ]

    class Meta:
        verbose_name = _("blog category")
        verbose_name_plural = _("blog categories")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class PostForm(WagtailAdminPageForm):
    """
    Pre-fills the author field with the current user when creating a new
    Post — "defaults to whoever publishes, but is editable": rather
    than a signal that silently overwrites author on publish (fights an
    editor who already set it, or credits whoever happened to click
    publish rather than who actually wrote it), this just pre-selects the
    field on a fresh draft; from then on it's a normal editable field like
    any other, never touched again by anything but the editor.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk is None and self.for_user is not None:
            # self.initial (not self.fields["author"].initial) — ModelForm's
            # __init__ (already run via super() above) builds self.initial
            # from model_to_dict() on the new/unsaved instance, which
            # includes "author": None as an explicit key. Form.
            # get_initial_for_field() checks self.initial before ever
            # falling back to the field's own .initial, so setting
            # self.fields["author"].initial here would be silently shadowed
            # by that pre-existing None and never actually render as the
            # field's pre-selected value.
            self.initial["author"] = self.for_user.pk


# ---------------------------------------------------------------------------
# Concrete page models
# ---------------------------------------------------------------------------

ITEMS_PER_PAGE = 12


class HomePage(BasePage, HeroMixin):
    """
    Site home page.

    Combines a full hero section (from HeroMixin) with a flexible StreamField
    body. Intended as the root page of the site.

    The only page type using HeroMixin's "full" hero variant (see
    HeroMixin.hero_variant) — every other page type gets the compact
    "banner" variant instead.

    A HomePage may also be nested under another HomePage. That is the
    country/region sub-home pattern (350.org/canada, 350.org/africa): a
    landing page that is structurally a home page — full-viewport hero with
    its own CTA, self-contained campaign body — rather than an article. It
    is deliberately *only* allowed under another HomePage, not under
    ContentPage or IndexPage, so "home page" keeps meaning "top of a site or
    of a region" instead of becoming a general-purpose page type.
    """

    template = "wtrx/pages/home_page.html"
    hero_variant = "full"

    body = StreamField(
        BodyStreamBlock(),
        blank=True,
        verbose_name=_("body"),
        help_text=_("Page body content."),
        use_json_field=True,
    )
    use_transparent_header = models.BooleanField(
        default=False,
        verbose_name=_("transparent header"),
        help_text=_(
            "Make the header transparent so the hero image extends behind it. "
            "Automatically uses the dark logo variant when enabled."
        ),
    )

    content_panels = (
        BasePage.title_panels
        + HeroMixin.hero_panels
        + [
            FieldPanel("body"),
            MultiFieldPanel(
                [FieldPanel("use_transparent_header")],
                heading=_("Header options"),
            ),
        ]
    )

    promote_panels = BasePage.promote_panels
    settings_panels = BasePage.settings_panels

    edit_handler = TabbedInterface(
        [
            ObjectList(content_panels, heading=_("Content")),
            ObjectList(promote_panels, heading=_("Promote")),
            ObjectList(settings_panels, heading=_("Settings")),
        ]
    )

    parent_page_types = ["wagtailcore.Page", "wtrx.HomePage"]
    subpage_types = [
        "wtrx.HomePage",
        "wtrx.ContentPage",
        "wtrx.IndexPage",
        "wtrx.FormPage",
        "wtrx.Blogs",
    ]

    class Meta:
        verbose_name = _("home page")
        verbose_name_plural = _("home pages")

    def get_context(self, request, *args, **kwargs):
        ctx = super().get_context(request, *args, **kwargs)
        ctx["hero"] = self.get_hero_context()
        ctx["transparent_header"] = self.use_transparent_header
        return ctx


class ContentPage(BasePage, HeroMixin):
    """
    General-purpose content page.

    Combines a hero section (from HeroMixin) with a flexible StreamField body.
    Can be used for about pages, blog posts, campaign pages, and any freeform
    content that doesn't need automatic child-page listing.
    """

    template = "wtrx/pages/content_page.html"

    body = StreamField(
        BodyStreamBlock(),
        blank=True,
        verbose_name=_("body"),
        help_text=_("Page body content."),
        use_json_field=True,
    )

    content_panels = (
        BasePage.title_panels
        + HeroMixin.banner_hero_panels
        + [
            FieldPanel("body"),
        ]
    )

    promote_panels = BasePage.promote_panels
    settings_panels = BasePage.settings_panels

    edit_handler = TabbedInterface(
        [
            ObjectList(content_panels, heading=_("Content")),
            ObjectList(promote_panels, heading=_("Promote")),
            ObjectList(settings_panels, heading=_("Settings")),
        ]
    )

    parent_page_types = [
        "wtrx.HomePage",
        "wtrx.ContentPage",
        "wtrx.IndexPage",
    ]
    subpage_types = [
        "wtrx.ContentPage",
        "wtrx.IndexPage",
        "wtrx.FormPage",
        "wtrx.Blogs",
    ]

    class Meta:
        verbose_name = _("content page")
        verbose_name_plural = _("content pages")

    def get_context(self, request, *args, **kwargs):
        ctx = super().get_context(request, *args, **kwargs)
        ctx["hero"] = self.get_hero_context()
        return ctx


class IndexPage(BasePage, HeroMixin):
    """
    Index / listing page.

    Displays a hero, optional intro text, and an auto-generated card grid of
    all live, public child pages (any type), paginated at ITEMS_PER_PAGE per
    page. An optional StreamField body appears below the child listing.
    """

    template = "wtrx/pages/index_page.html"

    intro = RichTextField(
        blank=True,
        features=RICHTEXT_FEATURES_INLINE,
        verbose_name=_("intro"),
        help_text=_(
            "Optional introductory text displayed above the child page listing."
        ),
    )
    body = StreamField(
        BodyStreamBlock(),
        blank=True,
        verbose_name=_("body"),
        help_text=_("Optional body content displayed below the child page listing."),
        use_json_field=True,
    )

    content_panels = (
        BasePage.title_panels
        + HeroMixin.banner_hero_panels
        + [
            FieldPanel("intro"),
            FieldPanel("body"),
        ]
    )

    promote_panels = BasePage.promote_panels
    settings_panels = BasePage.settings_panels

    edit_handler = TabbedInterface(
        [
            ObjectList(content_panels, heading=_("Content")),
            ObjectList(promote_panels, heading=_("Promote")),
            ObjectList(settings_panels, heading=_("Settings")),
        ]
    )

    parent_page_types = [
        "wtrx.HomePage",
        "wtrx.ContentPage",
        "wtrx.IndexPage",
    ]
    subpage_types = [
        "wtrx.ContentPage",
        "wtrx.IndexPage",
        "wtrx.FormPage",
        "wtrx.Blogs",
    ]

    class Meta:
        verbose_name = _("index page")
        verbose_name_plural = _("index pages")

    def get_context(self, request, *args, **kwargs):
        ctx = super().get_context(request, *args, **kwargs)

        ctx["hero"] = self.get_hero_context()

        children_qs = (
            self.get_children()
            .live()
            .public()
            .specific()
            # TODO: order_by("title") uses the database title field, not the
            # translated title from wagtail-localize. On a multilingual site,
            # child page ordering may be inconsistent across locales.
            .order_by("title")
        )
        paginator = Paginator(children_qs, ITEMS_PER_PAGE)
        page_number = request.GET.get("page", 1)
        try:
            children = paginator.page(page_number)
        except PageNotAnInteger:
            children = paginator.page(1)
        except EmptyPage:
            children = paginator.page(paginator.num_pages)

        ctx["children"] = children
        ctx["paginator"] = paginator
        return ctx


def _first_image_in_body(value):
    """
    Depth-first search for the first real image anywhere inside a body
    StreamField value. Backs Post.get_card_image()'s fallback for a post
    with no explicit header image.

    Recurses through every StreamValue/StructValue/ListValue container
    Wagtail can produce here -- the same three-type walk
    harvest_block_previews._richness() already uses to score a whole
    StreamField, just short-circuiting on the first hit instead of summing
    everything. That means it reaches into SectionBlock's own nested
    content stream and into every card/image/logo/person grid's list
    items with no hardcoded list of "blocks that might contain an image",
    and needs no changes when a new block type is added later.

    Every image-carrying block in this codebase names its ImageChooserBlock
    field `image` (ImageBlock, ImageTextBlock, FeaturePanelBlock, HeroBlock,
    QuoteBlock, CalloutBlock, DonateFundraiseUpBlock, SignupActionKitBlock/
    HeroSignupActionKitBlock, CardBlock, PersonCardBlock, ImageGridItemBlock,
    LogoGridItemBlock -- CardBlock's separate `icon` field is deliberately
    not matched), so this looks for that one field name rather than
    branching on block type. It returns the first one found in document
    order and stops there: this is a "better than a blank card" fallback,
    not a curated "best photo in the post" pick, so it makes no attempt to
    skip a more decorative image (e.g. CalloutBlock's background wash) in
    favor of a later, more "content" one.
    """
    if isinstance(value, StreamValue):
        for child in value:
            found = _first_image_in_body(child.value)
            if found:
                return found
        return None
    if isinstance(value, StructValue):
        for key, sub_value in value.items():
            if key == "image":
                if sub_value:
                    return sub_value
                continue
            found = _first_image_in_body(sub_value)
            if found:
                return found
        return None
    if isinstance(value, ListValue):
        for item in value:
            found = _first_image_in_body(item)
            if found:
                return found
        return None
    return None


class Post(BasePage, PublishedDateMixin, BannerHeroMixin):
    """
    A single post — covers both blog posts and press releases, which share
    an identical shape (see PLAN.md); author and categories are both
    optional, so a press-release-style post simply leaves them blank.

    published_at (PublishedDateMixin) is the editable display/ordering
    date; author defaults to whoever creates the post (PostForm) but
    stays freely editable afterwards; categories is an editor-managed
    multi-select against the BlogCategory snippet. Header is
    BannerHeroMixin's compact "banner" style (same look as ContentPage's
    header) with author/date folded in — see get_context(). When author
    and hero_image are left blank (e.g. an official statement with no
    byline), the banner just renders the title and date.
    """

    template = "wtrx/pages/post_page.html"
    base_form_class = PostForm

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("author"),
        help_text=_("Defaults to whoever creates this post. Editable."),
    )
    author_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("author name"),
        help_text=_(
            "Byline for a guest writer or imported post who doesn't have a "
            "site account. Ignored if Author (above) is set."
        ),
    )
    author_title = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("author title"),
        help_text=_(
            "Optional role/affiliation shown next to Author name, e.g. "
            "\"Senior Campaigner at Oil Change International\"."
        ),
    )
    categories = ParentalManyToManyField(
        "wtrx.BlogCategory",
        blank=True,
        related_name="posts",
        verbose_name=_("categories"),
    )
    body = StreamField(
        BodyStreamBlock(),
        blank=True,
        verbose_name=_("body"),
        help_text=_("Page body content."),
        use_json_field=True,
    )

    content_panels = (
        BasePage.title_panels
        + BannerHeroMixin.banner_hero_panels
        + PublishedDateMixin.published_date_panels
        + [
            FieldPanel("author"),
            FieldPanel("author_name"),
            FieldPanel("author_title"),
            FieldPanel("categories", widget=forms.CheckboxSelectMultiple),
            FieldPanel("body"),
        ]
    )

    promote_panels = BasePage.promote_panels
    settings_panels = BasePage.settings_panels

    edit_handler = TabbedInterface(
        [
            ObjectList(content_panels, heading=_("Content")),
            ObjectList(promote_panels, heading=_("Promote")),
            ObjectList(settings_panels, heading=_("Settings")),
        ]
    )

    parent_page_types = ["wtrx.Blogs"]
    subpage_types = []

    class Meta:
        verbose_name = _("post")
        verbose_name_plural = _("posts")

    @property
    def author_display(self):
        """
        Byline text for this post: the site account's name if Author (FK) is
        set, else the guest/imported Author name (+ title), else None.
        Shared by the hero banner and the Blogs listing cards so the
        two never drift out of sync.
        """
        if self.author_id:
            return self.author.get_full_name() or self.author.get_username()
        if self.author_name:
            if self.author_title:
                return f"{self.author_name}, {self.author_title}"
            return self.author_name
        return None

    def get_card_image(self):
        """
        This post's card/listing image, used wherever it's shown as a card
        (the Blogs index, PageCardsBlock, and its own "Related posts" panel
        on other posts -- see get_context() below and Blogs.get_context()).

        Prefers the explicit header image (hero_image, from BannerHeroMixin);
        falls back to the first image found anywhere in this post's body
        StreamField (see _first_image_in_body() for the search rules), so a
        post an editor never set a header image on still gets a
        representative thumbnail instead of a blank card. Returns None --
        not an error -- if neither is set; post_card.html already degrades
        gracefully with no image (AGENTS.md Error Handling).
        """
        if self.hero_image_id:
            return self.hero_image
        return _first_image_in_body(self.body)

    def get_context(self, request, *args, **kwargs):
        from wtrx.templatetags.wtrx_tags import page_as_card

        ctx = super().get_context(request, *args, **kwargs)
        parent = self.get_parent().specific
        ctx["hero"] = self.get_banner_hero_context(
            author=self.author_display,
            published_at=self.published_at,
            tag=parent.title,
            tag_url=parent.url,
        )

        # "Related <posts>" — the 3 most recent other live/public posts under
        # this post's own Blogs parent, per Figma's fixed (non-editor-
        # configurable) section at the bottom of every post. Same card
        # conversion PageCardsBlock/Blogs.get_context() use.
        #
        # Headings adapt to whichever Blogs page this post lives under, so a
        # post under "Press Releases" reads "Related press releases" /
        # "Read more press releases" with no per-page configuration — see
        # Blogs.post_label / Blogs.get_related_intro().
        related = (
            Post.objects.child_of(parent)
            .live()
            .public()
            .exclude(pk=self.pk)
            .order_by("-published_at")[:3]
        )
        related_posts = []
        for post in related:
            card = page_as_card(post)
            card["image"] = post.get_card_image()
            card["date"] = post.published_at
            related_posts.append(card)
        ctx["related_posts"] = related_posts
        ctx["parent_page"] = parent
        label = getattr(parent, "post_label", None) or _("posts")
        ctx["related_heading"] = _("Related %(label)s") % {"label": label}
        ctx["related_link_text"] = _("Read more %(label)s") % {"label": label}
        ctx["related_intro"] = (
            parent.get_related_intro() if hasattr(parent, "get_related_intro") else ""
        )

        return ctx


class Blogs(BasePage, HeroMixin):
    """
    Post listing page — covers both blog posts and press releases, since
    Post itself covers both (see PLAN.md).

    Live/public Post children, newest first by published_at, optionally
    filtered to one category via ?category=<slug>. The filter row (see
    blogs_page.html) only lists categories actually used by this page's own
    posts, so it disappears on its own for a page whose posts never carry
    categories (e.g. a press-release-only Blogs page) — see get_context().
    Unlike the generic IndexPage (which lists any child page type, ordered
    by title), this is specific to Post and its date/category semantics.

    Uses HeroMixin's "banner" default variant (per Figma's "Blog" hero) —
    hero_headline/hero_copy cover what a separate "intro" field used to,
    so there's no dedicated intro field here.

    Also supplies the copy for the "Related <posts>" section at the bottom
    of each of its child posts (see Post.get_context()), so that section
    adapts to the index page a post lives under instead of always saying
    "blogs".
    """

    template = "wtrx/pages/blogs_page.html"

    related_intro = models.TextField(
        blank=True,
        verbose_name=_("related posts intro"),
        help_text=_(
            "Supporting copy under the \"Related …\" heading at the bottom of "
            "each post under this page. Falls back to this page's header copy "
            "when blank."
        ),
    )

    content_panels = BasePage.title_panels + HeroMixin.banner_hero_panels + [FieldPanel("related_intro")]

    promote_panels = BasePage.promote_panels
    settings_panels = BasePage.settings_panels

    edit_handler = TabbedInterface(
        [
            ObjectList(content_panels, heading=_("Content")),
            ObjectList(promote_panels, heading=_("Promote")),
            ObjectList(settings_panels, heading=_("Settings")),
        ]
    )

    parent_page_types = [
        "wtrx.HomePage",
        "wtrx.ContentPage",
        "wtrx.IndexPage",
    ]
    subpage_types = ["wtrx.Post"]

    class Meta:
        verbose_name = _("Blogs")
        verbose_name_plural = _("Blogs")

    @property
    def post_label(self):
        """
        Lowercase plural noun for this page's posts, used to build the
        "Related …" / "Read more …" headings on each child Post (see
        Post.get_context()). Derived from the page title so a "Press
        Releases" page reads "press releases" and a "Blog" page reads
        "blogs" with nothing for an editor to configure — pluralisation is
        deliberately naive (append "s" unless the title already ends in
        one), since the title is the only signal available.
        """
        label = self.title.strip().lower()
        if not label:
            return ""
        if not label.endswith("s"):
            label = f"{label}s"
        return label

    def get_related_intro(self):
        """
        Supporting copy for a child Post's "Related …" section: the
        editor-set related_intro, else this page's own header copy with
        markup stripped (hero_copy is a RichTextField, the section renders
        plain text), else "".
        """
        if self.related_intro:
            return self.related_intro
        return strip_tags(self.hero_copy or "").strip()

    def get_listing_queryset(self):
        """
        This page's live/public posts, newest first by the editor-controlled
        published_at (not Wagtail's own first_published_at — see
        PublishedDateMixin).

        A method rather than an inline query so PageCardsBlock can list the
        same posts in the same order this page's own listing uses; a card
        row on the home page and the index it links to must never disagree
        about which posts are the most recent.
        """
        return Post.objects.child_of(self).live().public().order_by("-published_at")

    def get_context(self, request, *args, **kwargs):
        ctx = super().get_context(request, *args, **kwargs)
        ctx["hero"] = self.get_hero_context()

        posts_qs = self.get_listing_queryset()

        # Scoped to categories actually used by this page's own posts (not
        # every BlogCategory site-wide) so the filter row disappears on its
        # own wherever it doesn't apply — e.g. a press-release-only Blogs
        # page, where posts never carry categories — with no separate
        # toggle for editors to manage.
        available_categories = BlogCategory.objects.filter(posts__in=posts_qs).distinct()

        selected_category = None
        category_slug = request.GET.get("category")
        if category_slug:
            selected_category = available_categories.filter(slug=category_slug).first()
            if selected_category:
                posts_qs = posts_qs.filter(categories=selected_category)

        paginator = Paginator(posts_qs, ITEMS_PER_PAGE)
        page_number = request.GET.get("page", 1)
        try:
            posts = paginator.page(page_number)
        except PageNotAnInteger:
            posts = paginator.page(1)
        except EmptyPage:
            posts = paginator.page(paginator.num_pages)

        from wtrx.templatetags.wtrx_tags import page_as_card

        cards = []
        for post in posts:
            card = page_as_card(post)
            card["image"] = post.get_card_image()
            card["date"] = post.published_at
            cards.append(card)

        ctx["posts"] = posts
        ctx["cards"] = cards
        ctx["paginator"] = paginator
        ctx["categories"] = available_categories
        ctx["selected_category"] = selected_category
        return ctx


class FormField(AbstractFormField):
    """
    A single field in a FormPage's form builder.

    Uses ParentalKey so form fields are treated as child objects of FormPage
    and serialised correctly by Wagtail's modelcluster/page machinery.
    """

    page = ParentalKey(
        "FormPage",
        on_delete=models.CASCADE,
        related_name="form_fields",
    )


class FormPage(BasePage, AbstractEmailForm):
    """
    A Wagtail form builder page.

    Editors define form fields via the inline panel. Submissions are stored
    in the Wagtail DB and optionally emailed. The form is rendered inline
    on any page that contains a SignupWagtailFormsBlock pointing to this page.

    MRO note: BasePage must come before AbstractEmailForm to keep Wagtail's
    page machinery (slug, tree, routing) in the correct resolution order.

    content_panels is explicitly defined starting from BasePage.title_panels
    (BasePage itself has no content_panels of its own, so there's no MRO
    ambiguity to worry about here).

    Future: override process_form_submission() to also forward submissions to
    Action Network when that integration is enabled. See PLAN.md FormPage
    notes for the full forwarding design.
    """

    template = "wtrx/pages/form_page.html"

    intro = RichTextField(
        blank=True,
        features=RICHTEXT_FEATURES_INLINE,
        verbose_name=_("intro"),
        help_text=_("Optional introductory text displayed above the form."),
    )
    thank_you_text = RichTextField(
        blank=True,
        features=RICHTEXT_FEATURES_INLINE,
        verbose_name=_("thank you text"),
        help_text=_("Text displayed after a successful form submission."),
    )
    actionkit_page = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("ActionKit page name"),
        help_text=_(
            "The ActionKit page short name this form submits to. Only used when "
            "the ActionKit integration (Settings → Integrations) is enabled. "
            "Leave blank to disable ActionKit forwarding for this form."
        ),
    )

    # Explicitly defined on FormPage itself (not inherited) — BasePage has no
    # content_panels of its own (only the reusable title_panels list, mixed
    # in explicitly here), so there's no MRO ambiguity to worry about despite
    # FormPage(BasePage, AbstractEmailForm)'s multiple inheritance.
    content_panels = BasePage.title_panels + [
        FieldPanel("intro"),
        InlinePanel("form_fields", label=_("Form fields")),
        FieldPanel("thank_you_text"),
        MultiFieldPanel(
            [
                FieldPanel("to_address"),
                FieldPanel("from_address"),
                FieldPanel("subject"),
            ],
            heading=_("Email notifications"),
        ),
        MultiFieldPanel(
            [FieldPanel("actionkit_page")],
            heading=_("ActionKit"),
        ),
    ]

    promote_panels = BasePage.promote_panels
    settings_panels = BasePage.settings_panels

    edit_handler = TabbedInterface(
        [
            ObjectList(content_panels, heading=_("Content")),
            ObjectList(promote_panels, heading=_("Promote")),
            ObjectList(settings_panels, heading=_("Settings")),
        ]
    )

    parent_page_types = [
        "wtrx.HomePage",
        "wtrx.ContentPage",
        "wtrx.IndexPage",
    ]
    subpage_types = []

    class Meta:
        verbose_name = _("form page")
        verbose_name_plural = _("form pages")

    def get_context(self, request, *args, **kwargs):
        ctx = super().get_context(request, *args, **kwargs)
        # FormPage has no HeroMixin, so there are no hero_* fields on the model.
        # We still build the hero dict so that components/hero.html can render a
        # consistent title-only heading bar without branching on page type.
        # All optional keys are None; headline is always the page title.
        ctx["hero"] = {
            "headline": self.title,
            "copy": None,
            "copy_is_block": False,
            "image": None,
            "video": None,
            "cta": [],
        }
        return ctx

    def process_form_submission(self, form):
        """
        Store the submission normally (Wagtail DB + email), then forward it to
        ActionKit when the signup platform is set to ActionKit and this form has
        an ActionKit page configured.

        Forwarding is best-effort: any failure (misconfiguration, API error, or
        network error) is logged and swallowed so it never blocks the user's
        signup. The local submission is always saved first and returned.
        """
        submission = super().process_form_submission(form)

        try:
            integration = IntegrationSettings.for_site(self.get_site())
            actionkit_config = integration.get_integration_config("actionkit")
            if actionkit_config and self.actionkit_page:
                fields = actionkit.map_form_fields(form.cleaned_data)
                if fields.get("email"):
                    actionkit.submit_action(
                        actionkit_config.get("hostname"),
                        actionkit_config.get("api_username"),
                        integration.get_actionkit_api_password(),
                        self.actionkit_page,
                        fields,
                    )
                else:
                    logger.warning(
                        "ActionKit forwarding skipped for FormPage %s: no email in submission.",
                        self.pk,
                    )
        except Exception:
            logger.exception("ActionKit forwarding failed for FormPage %s.", self.pk)

        return submission

    def serve(self, request, *args, **kwargs):
        if request.method == "POST":
            form = self.get_form(
                request.POST, request.FILES, page=self, user=request.user
            )
            if form.is_valid():
                form_submission = self.process_form_submission(form)
                return self.render_landing_page(request, form_submission)
            elif request.headers.get("X-Requested-With") == "XMLHttpRequest":
                # AJAX invalid POST: return JSON 400 with field errors.
                # Non-AJAX invalid POST: fall through to super().serve() below.
                # AbstractEmailForm.serve() independently re-binds the form from
                # request.POST and re-renders the template with validation errors —
                # this is intentional and is the standard AbstractEmailForm pattern.
                errors = {
                    field: [str(e) for e in errs] for field, errs in form.errors.items()
                }
                return JsonResponse({"success": False, "errors": errors}, status=400)
        return super().serve(request, *args, **kwargs)

    def render_landing_page(self, request, form_submission=None, *args, **kwargs):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        return super().render_landing_page(request, form_submission, *args, **kwargs)

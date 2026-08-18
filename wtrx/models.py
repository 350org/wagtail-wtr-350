import logging

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from wagtail.admin.panels import (
    FieldPanel,
    InlinePanel,
    MultiFieldPanel,
    ObjectList,
    TabbedInterface,
)
from wagtail.contrib.forms.models import AbstractEmailForm, AbstractFormField
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Page
from wagtailmedia.edit_handlers import MediaChooserPanel

from .blocks import CALLOUT_COLOR_CHOICES, HERO_LAYOUT_CHOICES, BodyStreamBlock, HeroCTABlock
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

    promote_panels = Page.promote_panels + [
        MultiFieldPanel(
            [
                FieldPanel("meta_image"),
                FieldPanel("hide_from_search"),
            ],
            heading=_("SEO"),
        ),
    ]

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
    original full-viewport hero, background image or video, centered/left
    text, optional cta — or "banner" — a compact rounded panel, solid/
    gradient color background (reusing CalloutBlock's 5-color system) beside
    an image, no cta. Which variant a page gets is fixed per page type via
    the hero_variant class attribute, not editor-controlled: HomePage
    overrides it to "full"; every other HeroMixin page type (ContentPage,
    IndexPage) uses the "banner" default.

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
    - hero_layout: centered or left-aligned text. "full" variant only —
      "banner" has a fixed text-left/image-right structure.
    - hero_banner_color: background color/gradient. "banner" variant only —
      "full" never shows a solid color background.
    - hero_cta: optional signup/donate/announcement widget (HeroCTABlock, at
      most one). "full" variant only — "banner" never renders one.

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
    hero_layout = models.CharField(
        max_length=20,
        choices=HERO_LAYOUT_CHOICES,
        default="centered",
        verbose_name=_("hero layout"),
        help_text=_(
            "Centered text over the image, or left-aligned and anchored toward the bottom. "
            "Only affects the homepage's full-viewport hero — every other page's hero "
            "renders as a compact banner with a fixed layout."
        ),
    )
    hero_banner_color = models.CharField(
        max_length=20,
        choices=CALLOUT_COLOR_CHOICES,
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
                FieldPanel("hero_layout"),
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
            "layout": self.hero_layout,
            "banner_color": self.hero_banner_color,
            "cta": self.hero_cta,
        }

    class Meta:
        abstract = True


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
        Page.content_panels
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

    edit_handler = TabbedInterface(
        [
            ObjectList(content_panels, heading=_("Content")),
            ObjectList(promote_panels, heading=_("Promote")),
        ]
    )

    parent_page_types = ["wagtailcore.Page"]
    subpage_types = [
        "wtrx.ContentPage",
        "wtrx.IndexPage",
        "wtrx.FormPage",
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
        Page.content_panels
        + HeroMixin.hero_panels
        + [
            FieldPanel("body"),
        ]
    )

    promote_panels = BasePage.promote_panels

    edit_handler = TabbedInterface(
        [
            ObjectList(content_panels, heading=_("Content")),
            ObjectList(promote_panels, heading=_("Promote")),
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
        Page.content_panels
        + HeroMixin.hero_panels
        + [
            FieldPanel("intro"),
            FieldPanel("body"),
        ]
    )

    promote_panels = BasePage.promote_panels

    edit_handler = TabbedInterface(
        [
            ObjectList(content_panels, heading=_("Content")),
            ObjectList(promote_panels, heading=_("Promote")),
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

    content_panels is explicitly defined starting from
    AbstractEmailForm.content_panels (== Page.content_panels) to avoid the
    MRO resolving to BasePage.content_panels and dropping email fields.

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

    # Explicitly start from AbstractEmailForm.content_panels, which extends
    # Page.content_panels with the email notification fields (to_address, from_address,
    # subject). Do NOT use BasePage.content_panels here — Python's MRO would resolve
    # to BasePage.content_panels and drop those email fields entirely.
    content_panels = AbstractEmailForm.content_panels + [
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

    edit_handler = TabbedInterface(
        [
            ObjectList(content_panels, heading=_("Content")),
            ObjectList(promote_panels, heading=_("Promote")),
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
            "layout": "centered",
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

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel, TabbedInterface, ObjectList
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Page

from wagtail_wtr.wtrx.blocks import BodyStreamBlock
from wagtail_wtr.wtrx.constants import RICHTEXT_FEATURES_INLINE
from wagtail_wtr.wtrx.models import BasePage, HeroMixin

ITEMS_PER_PAGE = 12


class ContentPage(BasePage, HeroMixin):
    """
    General-purpose content page.

    Combines a hero section (from HeroMixin) with a flexible StreamField body.
    Can be used for about pages, blog posts, campaign pages, and any freeform
    content that doesn't need automatic child-page listing.
    """

    template = "pages/content_page.html"

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
        "wagtail_wtr_home.HomePage",
        "wagtail_wtr_pages.ContentPage",
        "wagtail_wtr_pages.IndexPage",
    ]
    subpage_types = [
        "wagtail_wtr_pages.ContentPage",
        "wagtail_wtr_pages.IndexPage",
        "wagtail_wtr_forms.FormPage",
    ]

    class Meta:
        verbose_name = _("content page")
        verbose_name_plural = _("content pages")

    def get_context(self, request, *args, **kwargs):
        ctx = super().get_context(request, *args, **kwargs)
        # Build the hero context dict consumed by components/hero.html.
        # See HomePage.get_context() for the full explanation of this pattern.
        ctx["hero"] = {
            "headline": self.hero_headline or self.title,
            "copy": self.hero_copy,
            "copy_is_block": False,
            "image": self.hero_image,
            "link_text": self.hero_link_text,
            "link_page": self.hero_link_page,
            "link_url": self.hero_link_url,
        }
        return ctx


class IndexPage(BasePage, HeroMixin):
    """
    Index / listing page.

    Displays a hero, optional intro text, and an auto-generated card grid of
    all live, public child pages (any type), paginated at 12 per page. An
    optional StreamField body appears below the child listing.
    """

    template = "pages/index_page.html"

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
        "wagtail_wtr_home.HomePage",
        "wagtail_wtr_pages.ContentPage",
        "wagtail_wtr_pages.IndexPage",
    ]
    subpage_types = [
        "wagtail_wtr_pages.ContentPage",
        "wagtail_wtr_pages.IndexPage",
        "wagtail_wtr_forms.FormPage",
    ]

    class Meta:
        verbose_name = _("index page")
        verbose_name_plural = _("index pages")

    def get_context(self, request, *args, **kwargs):
        ctx = super().get_context(request, *args, **kwargs)

        # Build the hero context dict consumed by components/hero.html.
        # See HomePage.get_context() for the full explanation of this pattern.
        ctx["hero"] = {
            "headline": self.hero_headline or self.title,
            "copy": self.hero_copy,
            "copy_is_block": False,
            "image": self.hero_image,
            "link_text": self.hero_link_text,
            "link_page": self.hero_link_page,
            "link_url": self.hero_link_url,
        }

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
        page_number = request.GET.get("page")
        try:
            children = paginator.page(page_number)
        except PageNotAnInteger:
            children = paginator.page(1)
        except EmptyPage:
            children = paginator.page(paginator.num_pages)

        ctx["children"] = children
        ctx["paginator"] = paginator
        return ctx

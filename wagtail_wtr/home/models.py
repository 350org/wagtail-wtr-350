from django.db import models
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import (
    FieldPanel,
    MultiFieldPanel,
    TabbedInterface,
    ObjectList,
)
from wagtail.fields import StreamField
from wagtail.models import Page

from wagtail_wtr.wtrx.blocks import BodyStreamBlock
from wagtail_wtr.wtrx.models import BasePage, HeroMixin


class HomePage(BasePage, HeroMixin):
    """
    Site home page.

    Combines a full hero section (from HeroMixin) with a flexible StreamField
    body. Intended as the root page of the site.
    """

    template = "wtrx/pages/home_page.html"

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
        "wagtail_wtr_pages.ContentPage",
        "wagtail_wtr_pages.IndexPage",
        "wagtail_wtr_forms.FormPage",
    ]

    class Meta:
        verbose_name = _("home page")
        verbose_name_plural = _("home pages")

    def get_context(self, request, *args, **kwargs):
        ctx = super().get_context(request, *args, **kwargs)
        # Build the hero context dict consumed by components/hero.html.
        # The same template is used by HeroBlock (StreamField) and all page types,
        # so every caller must provide this exact dict shape. Mapping is done here
        # in Python rather than in the template so that:
        #   - The headline fallback (hero_headline or page title) is in one place.
        #   - hero.html stays logic-free and works identically for pages and blocks.
        # copy_is_block=False because hero_copy is a RichTextField (string),
        # not a StreamField block value — the template renders it with |richtext.
        ctx["hero"] = {
            "headline": self.hero_headline or self.title,
            "copy": self.hero_copy,
            "copy_is_block": False,
            "image": self.hero_image,
            "video": self.hero_video,
            "link_text": self.hero_link_text,
            "link_page": self.hero_link_page,
            "link_url": self.hero_link_url,
        }
        ctx["transparent_header"] = self.use_transparent_header
        return ctx

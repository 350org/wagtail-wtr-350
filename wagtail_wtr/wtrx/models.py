from django.db import models
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Page

from .constants import RICHTEXT_FEATURES_HERO
from .images import CustomImage, CustomRendition  # noqa: F401 — register with Django ORM
from .site_settings import (  # noqa: F401 — register with Django ORM
    BrandingSEOSettings,
    FooterSettings,
    IntegrationSettings,
    NavigationSettings,
    SocialSettings,
)


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

    def get_sitemap_urls(self, request=None):
        if self.hide_from_search:
            return []
        return super().get_sitemap_urls(request)

    class Meta:
        abstract = True


class HeroMixin(models.Model):
    """
    Mixin adding a full hero section to any page type.

    Fields:
    - hero_headline: optional override for the page title as the displayed h1
    - hero_copy: optional subtext below the headline
    - hero_image: optional background/feature image
    - hero_link_text + hero_link_page / hero_link_url: optional CTA button

    Use: include `components/hero.html` in the page template.
    Exactly one of hero_link_page or hero_link_url should be set (not validated
    at model level — validated in the admin panel via help text guidance).
    """

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
        help_text=_("Optional hero background or feature image."),
    )
    hero_link_text = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("hero link text"),
        help_text=_("CTA button label. Required if a link is set."),
    )
    hero_link_page = models.ForeignKey(
        "wagtailcore.Page",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("hero link page"),
        help_text=_("Internal CTA link. Set either this or Hero link URL, not both."),
    )
    hero_link_url = models.URLField(
        blank=True,
        verbose_name=_("hero link URL"),
        help_text=_("External CTA link. Set either this or Hero link page, not both."),
    )

    hero_panels = [
        MultiFieldPanel(
            [
                FieldPanel("hero_headline"),
                FieldPanel("hero_copy"),
                FieldPanel("hero_image"),
                FieldPanel("hero_link_text"),
                FieldPanel("hero_link_page"),
                FieldPanel("hero_link_url"),
            ],
            heading=_("Hero"),
        ),
    ]

    class Meta:
        abstract = True

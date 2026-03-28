from django.db import models
from django.utils.translation import gettext_lazy as _
from wagtail.images.models import AbstractImage, AbstractRendition, Image


class CustomImage(AbstractImage):
    """
    Custom image model.

    Extends AbstractImage with a credit field for photographer/source attribution.
    Additional fields (copyright, license, etc.) can be added here without
    migrating away from Wagtail's built-in Image model.

    WAGTAILIMAGES_IMAGE_MODEL in settings/base.py points to this model.
    """

    credit = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("credit"),
        help_text=_("Photographer or source attribution (e.g. 'Photo: Jane Smith')."),
    )

    admin_form_fields = Image.admin_form_fields + ("credit",)

    class Meta(AbstractImage.Meta):
        verbose_name = _("image")
        verbose_name_plural = _("images")

    @property
    def object_position_style(self):
        """
        Returns a full CSS object-position declaration derived from the focal point.
        Use in templates: style="<value of page.hero_image.object_position_style>"
        Mirrors the convention of Wagtail's built-in background_position_style property.
        """
        if self.has_focal_point() and self.width and self.height:
            fp = self.get_focal_point()
            x = round(fp.centroid_x / self.width * 100)
            y = round(fp.centroid_y / self.height * 100)
            return f"object-position: {x}% {y}%;"
        return "object-position: center center;"


class CustomRendition(AbstractRendition):
    """Custom rendition for CustomImage."""

    image = models.ForeignKey(
        CustomImage,
        on_delete=models.CASCADE,
        related_name='renditions',
    )

    class Meta(AbstractRendition.Meta):
        unique_together = (('image', 'filter_spec', 'focal_point_key'),)

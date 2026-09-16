"""
Auto-optimize wagtailmedia video-thumbnail uploads.

wagtailmedia.models.Media.thumbnail is a plain FileField -- Wagtail's Image
rendition pipeline (resize, format conversion, caching) never touches it, so
whatever an editor uploads is served completely as-is. It's used in exactly
one role across this codebase, as a <video poster="...">:
wtrx/templates/wtrx/components/_hero_background_video.html (hero's
background video), .../streamfield/blocks/video_block.html, and
.../streamfield/blocks/accordion_block.html. It's never relied on elsewhere
at a particular size or quality, so resizing/recompressing it destructively
on upload is safe.

Confirmed live via a PageSpeed Insights "Improve image delivery" flag: a
hero video's thumbnail was an 831 KiB PNG (a raw design-tool export, judging
by its filename -- "Rectangle_130.png") served completely unresized as a
full-bleed background poster. wtrx/models.py's own help text tells editors
to "upload a thumbnail on the video" for exactly this poster-frame role, so
this is a data-quality gap in a deliberately-used feature, not a bug in the
fallback logic itself (see AGENTS.md architecture rule #4's poster fallback
chain).

connect_signals() below hooks pre_save on wagtailmedia.Media so every future
thumbnail upload is capped to MAX_THUMBNAIL_DIMENSION and re-encoded as JPEG
before it reaches storage -- a video poster is always rendered opaque
underneath the <video> element, so PNG's lossless/alpha features are wasted
bytes here regardless of the source format. The backfill_video_thumbnails
management command applies the same processing to existing Media rows.

Skips reprocessing on a save that doesn't touch thumbnail at all (compares
against the value already in the database), so editing a Media item's title
doesn't recompress its thumbnail on every save. Any processing failure is
logged and the original upload is left untouched rather than blocking the
save -- a bad optimization pass should never be the reason an editor can't
save their media.

Plain Pillow rather than Willow (Wagtail's own image library, used by
CustomImage/CustomRendition): Willow's newer plugin-registry API (operations
resolved dynamically per backend) makes a one-off "resize down, re-encode as
JPEG" task in a raw FileField pipeline more awkward than reaching for Pillow
directly, which Willow itself sits on top of anyway.
"""

import logging
import os
from io import BytesIO

from django.core.files.base import ContentFile
from django.db.models.signals import pre_save
from PIL import Image as PILImage

logger = logging.getLogger(__name__)

MAX_THUMBNAIL_DIMENSION = 1600
THUMBNAIL_JPEG_QUALITY = 82


def build_optimized_thumbnail(field_file):
    """
    Return a ContentFile holding an optimized JPEG version of field_file
    (capped to MAX_THUMBNAIL_DIMENSION on its longest side, transparency
    flattened onto white), or None if field_file can't be read as an image.
    """
    field_file.seek(0)
    try:
        image = PILImage.open(field_file)
        image.load()
    except Exception:
        return None

    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        image = image.convert("RGBA")
        background = PILImage.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1])
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    width, height = image.size
    longest_side = max(width, height)
    if longest_side > MAX_THUMBNAIL_DIMENSION:
        scale = MAX_THUMBNAIL_DIMENSION / longest_side
        image = image.resize(
            (round(width * scale), round(height * scale)),
            PILImage.Resampling.LANCZOS,
        )

    output = BytesIO()
    image.save(output, format="JPEG", quality=THUMBNAIL_JPEG_QUALITY, optimize=True)

    base_name = os.path.splitext(os.path.basename(field_file.name))[0]
    return ContentFile(output.getvalue(), name=f"{base_name}.jpg")


def optimize_media_thumbnail(sender, instance, **kwargs):
    """pre_save receiver for wagtailmedia.Media -- see module docstring."""
    if not instance.thumbnail:
        return

    if instance.pk:
        try:
            existing_name = sender.objects.only("thumbnail").get(pk=instance.pk).thumbnail.name
        except sender.DoesNotExist:
            existing_name = None
        if existing_name == instance.thumbnail.name:
            return  # thumbnail untouched by this save -- already processed, or intentionally left alone

    try:
        optimized = build_optimized_thumbnail(instance.thumbnail)
    except Exception:
        logger.exception(
            "wtrx media_optimization: failed to optimize thumbnail for Media pk=%s -- leaving upload as-is.",
            instance.pk,
        )
        return

    if optimized is not None:
        instance.thumbnail = optimized


def connect_signals():
    """Connect this module's signal handlers. Called from WtrxConfig.ready()."""
    from wagtailmedia.models import Media

    pre_save.connect(
        optimize_media_thumbnail,
        sender=Media,
        dispatch_uid="wtrx.media_optimization.optimize_media_thumbnail",
    )

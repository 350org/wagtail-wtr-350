"""
Tests for wtrx.media_optimization (auto-optimizing wagtailmedia video-poster
thumbnails -- see that module's docstring for the full rationale, prompted
by a PageSpeed Insights "Improve image delivery" flag on an 831 KiB raw PNG
hero-video thumbnail).
"""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models.signals import pre_save
from django.test import TestCase
from PIL import Image as PILImage
from wagtailmedia.models import Media

from wtrx.media_optimization import (
    MAX_THUMBNAIL_DIMENSION,
    build_optimized_thumbnail,
    optimize_media_thumbnail,
)


def _png_bytes(size, mode="RGB", color=(200, 50, 50)):
    buf = BytesIO()
    PILImage.new(mode, size, color).save(buf, format="PNG")
    return buf.getvalue()


def _make_media(name="clip.mp4", thumbnail_name="poster.png", thumbnail_bytes=None):
    """
    Create a Media row without triggering wtrx's own optimization signal --
    used to set up fixtures representing pre-existing, unoptimized uploads
    (the state this app's real data was in before this feature existed).
    """
    pre_save.disconnect(
        optimize_media_thumbnail, sender=Media, dispatch_uid="wtrx.media_optimization.optimize_media_thumbnail"
    )
    try:
        return Media.objects.create(
            title="Test video",
            file=SimpleUploadedFile(name, b"not-a-real-video", content_type="video/mp4"),
            type="video",
            thumbnail=SimpleUploadedFile(thumbnail_name, thumbnail_bytes, content_type="image/png"),
        )
    finally:
        pre_save.connect(
            optimize_media_thumbnail, sender=Media, dispatch_uid="wtrx.media_optimization.optimize_media_thumbnail"
        )


class TestBuildOptimizedThumbnail(TestCase):
    def test_resizes_an_oversized_image_down_to_the_max_dimension(self):
        media = _make_media(thumbnail_bytes=_png_bytes((2000, 1000)))
        result = build_optimized_thumbnail(media.thumbnail)
        image = PILImage.open(result)
        self.assertEqual(image.format, "JPEG")
        self.assertEqual(max(image.size), MAX_THUMBNAIL_DIMENSION)
        self.assertEqual(image.size, (MAX_THUMBNAIL_DIMENSION, MAX_THUMBNAIL_DIMENSION // 2))

    def test_leaves_dimensions_alone_when_already_within_the_max(self):
        media = _make_media(thumbnail_bytes=_png_bytes((400, 300)))
        result = build_optimized_thumbnail(media.thumbnail)
        image = PILImage.open(result)
        self.assertEqual(image.size, (400, 300))

    def test_output_is_always_jpeg_regardless_of_source_format(self):
        media = _make_media(thumbnail_bytes=_png_bytes((400, 300)))
        result = build_optimized_thumbnail(media.thumbnail)
        self.assertTrue(result.name.endswith(".jpg"))
        self.assertEqual(PILImage.open(result).format, "JPEG")

    def test_flattens_transparency_onto_white_rather_than_black(self):
        media = _make_media(thumbnail_bytes=_png_bytes((10, 10), mode="RGBA", color=(255, 0, 0, 0)))
        result = build_optimized_thumbnail(media.thumbnail)
        image = PILImage.open(result).convert("RGB")
        self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))

    def test_returns_none_for_undecodable_bytes(self):
        media = _make_media(thumbnail_name="poster.png", thumbnail_bytes=b"not actually an image")
        self.assertIsNone(build_optimized_thumbnail(media.thumbnail))

    def test_output_is_meaningfully_smaller_for_a_large_flat_color_png(self):
        media = _make_media(thumbnail_bytes=_png_bytes((2000, 1000)))
        original_size = media.thumbnail.size
        result = build_optimized_thumbnail(media.thumbnail)
        self.assertLess(len(result.read()), original_size)


class TestOptimizeMediaThumbnailSignal(TestCase):
    def test_new_upload_is_optimized_on_create(self):
        media = Media.objects.create(
            title="Test video",
            file=SimpleUploadedFile("clip.mp4", b"not-a-real-video", content_type="video/mp4"),
            type="video",
            thumbnail=SimpleUploadedFile("Rectangle_130.png", _png_bytes((2000, 1000)), content_type="image/png"),
        )
        self.assertTrue(media.thumbnail.name.endswith(".jpg"))
        image = PILImage.open(media.thumbnail)
        self.assertEqual(max(image.size), MAX_THUMBNAIL_DIMENSION)

    def test_unrelated_save_does_not_reprocess_the_thumbnail(self):
        media = Media.objects.create(
            title="Test video",
            file=SimpleUploadedFile("clip.mp4", b"not-a-real-video", content_type="video/mp4"),
            type="video",
            thumbnail=SimpleUploadedFile("poster.png", _png_bytes((400, 300)), content_type="image/png"),
        )
        first_name = media.thumbnail.name

        media.title = "Renamed video"
        media.save()

        media.refresh_from_db()
        self.assertEqual(media.thumbnail.name, first_name)

    def test_replacing_the_thumbnail_reprocesses_it(self):
        media = Media.objects.create(
            title="Test video",
            file=SimpleUploadedFile("clip.mp4", b"not-a-real-video", content_type="video/mp4"),
            type="video",
            thumbnail=SimpleUploadedFile("poster.png", _png_bytes((400, 300)), content_type="image/png"),
        )
        first_name = media.thumbnail.name

        media.thumbnail = SimpleUploadedFile("new-poster.png", _png_bytes((2000, 1000)), content_type="image/png")
        media.save()

        media.refresh_from_db()
        self.assertNotEqual(media.thumbnail.name, first_name)
        self.assertEqual(max(PILImage.open(media.thumbnail).size), MAX_THUMBNAIL_DIMENSION)

    def test_undecodable_thumbnail_is_left_alone_rather_than_blocking_save(self):
        media = Media.objects.create(
            title="Test video",
            file=SimpleUploadedFile("clip.mp4", b"not-a-real-video", content_type="video/mp4"),
            type="video",
            thumbnail=SimpleUploadedFile("poster.png", b"not actually an image", content_type="image/png"),
        )
        self.assertEqual(media.thumbnail.read(), b"not actually an image")


class TestBackfillVideoThumbnailsCommand(TestCase):
    def test_dry_run_reports_without_changing_anything(self):
        media = _make_media(thumbnail_bytes=_png_bytes((2000, 1000)))
        original_name = media.thumbnail.name

        call_command("backfill_video_thumbnails", "--dry-run")

        media.refresh_from_db()
        self.assertEqual(media.thumbnail.name, original_name)

    def test_apply_optimizes_an_existing_oversized_thumbnail(self):
        media = _make_media(thumbnail_bytes=_png_bytes((2000, 1000)))

        call_command("backfill_video_thumbnails")

        media.refresh_from_db()
        self.assertTrue(media.thumbnail.name.endswith(".jpg"))
        self.assertEqual(max(PILImage.open(media.thumbnail).size), MAX_THUMBNAIL_DIMENSION)

    def test_media_id_filters_to_a_single_item(self):
        target = _make_media(thumbnail_bytes=_png_bytes((2000, 1000)))
        other = _make_media(thumbnail_bytes=_png_bytes((2000, 1000)))

        call_command("backfill_video_thumbnails", "--media-id", str(target.pk))

        target.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(target.thumbnail.name.endswith(".jpg"))
        self.assertFalse(other.thumbnail.name.endswith(".jpg"))

    def test_undecodable_thumbnail_is_reported_not_treated_as_an_error(self):
        _make_media(thumbnail_name="poster.png", thumbnail_bytes=b"not actually an image")
        # Should not raise.
        call_command("backfill_video_thumbnails")

    def test_does_not_leave_the_signal_disconnected_after_running(self):
        call_command("backfill_video_thumbnails")

        media = Media.objects.create(
            title="Test video",
            file=SimpleUploadedFile("clip.mp4", b"not-a-real-video", content_type="video/mp4"),
            type="video",
            thumbnail=SimpleUploadedFile("poster.png", _png_bytes((2000, 1000)), content_type="image/png"),
        )
        self.assertTrue(media.thumbnail.name.endswith(".jpg"))

"""
Downsize existing CustomImage rows whose original upload exceeds
_wp_content_utils.MAX_IMPORTED_IMAGE_DIMENSION on its longest side.

New imports via import_350_blog.py/import_350_press_releases.py (both routed
through _wp_content_utils.download_image()) are unaffected by this command:
they're already downsized at import time by that function's own call to
downsize_oversized_image(). This is a one-time fix for images imported
before that existed -- notably a WordPress "full size" upload URL that
turned out to be a raw 8192x5464 (44.8MP) original, which OOM-killed a live
worker generating a mere fill-640x360 card thumbnail the first time anyone
requested it (Wagtail's rendition pipeline always fully decodes the source
before resizing down, for any filter spec, regardless of the requested
output size). See _wp_content_utils.downsize_oversized_image's own
docstring for the full story.

Deletes the image's existing renditions after replacing its file -- they
were generated from the old (oversized) original and would otherwise keep
serving stale cached copies alongside the new, smaller source.

    python manage.py backfill_oversized_images --dry-run
    python manage.py backfill_oversized_images
    python manage.py backfill_oversized_images --image-id 592
"""

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from wtrx.management.commands._wp_content_utils import (
    MAX_IMPORTED_IMAGE_DIMENSION,
    downsize_oversized_image,
)


class Command(BaseCommand):
    help = "Resize existing CustomImage originals that exceed MAX_IMPORTED_IMAGE_DIMENSION."

    def add_arguments(self, parser):
        parser.add_argument(
            "--image-id",
            type=int,
            default=None,
            help="Only process this single CustomImage ID.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        from wtrx.images import CustomImage

        images = CustomImage.objects.order_by("pk")
        if options["image_id"] is not None:
            images = images.filter(pk=options["image_id"])
        dry_run = options["dry_run"]

        checked = updated = unreadable = failed = 0
        for image in images:
            checked += 1
            if max(image.width, image.height) <= MAX_IMPORTED_IMAGE_DIMENSION:
                continue

            try:
                image.file.open("rb")
                original_content = image.file.read()
            except Exception as exc:  # noqa: BLE001 -- report and keep going
                self.stderr.write(self.style.WARNING(f"  FAILED (read): {image.pk} {image.title} — {exc}"))
                failed += 1
                continue
            finally:
                image.file.close()

            original_dimensions = f"{image.width}x{image.height}"
            resized_content = downsize_oversized_image(original_content, image.title, self.stdout)
            if resized_content is original_content:
                # Couldn't decode/resize -- downsize_oversized_image already
                # logged why.
                self.stdout.write(f"  skip (could not downsize): {image.pk} {image.title}")
                unreadable += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"  [dry-run] {image.pk} {image.title}: {original_dimensions} "
                    f"-> capped to {MAX_IMPORTED_IMAGE_DIMENSION}px"
                )
                updated += 1
                continue

            image.file = ContentFile(resized_content, name=image.title)
            image.save()
            image.renditions.all().delete()
            self.stdout.write(
                f"  updated: {image.pk} {image.title}: {original_dimensions} -> {image.width}x{image.height}"
            )
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nChecked {checked} image(s), {'would update' if dry_run else 'updated'} {updated}, "
                f"{unreadable} unreadable, {failed} failed."
            )
        )

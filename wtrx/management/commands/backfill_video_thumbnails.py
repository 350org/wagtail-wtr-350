"""
Optimize existing wagtailmedia.Media thumbnails that predate
wtrx.media_optimization's pre_save hook (see that module's docstring for the
full rationale -- confirmed live via a PageSpeed Insights "Improve image
delivery" flag on a hero video's 831 KiB raw PNG thumbnail).

New thumbnail uploads are unaffected by this command: they're already
optimized on save by wtrx.media_optimization.optimize_media_thumbnail. This
is a one-time fix for Media rows created before that hook existed.

Disconnects that same pre_save hook for the duration of the run (reconnected
in a finally block): this command already builds the optimized file itself
via build_optimized_thumbnail and calls Media.save() to persist it, and the
hook's own "already processed?" check compares the instance's thumbnail name
against the database's -- which would never match here (an optimized name
always differs from the original), so without disconnecting, every row
would get reprocessed a second, redundant time (another recompression pass,
plus a second wasted storage write) as a side effect of this command's own
save() call.

Skips a thumbnail whose bytes can't be decoded as an image (build_optimized_
thumbnail returns None) and reports it, rather than aborting the run.

    python manage.py backfill_video_thumbnails --dry-run
    python manage.py backfill_video_thumbnails
    python manage.py backfill_video_thumbnails --media-id 42
"""

from django.core.management.base import BaseCommand
from django.db.models.signals import pre_save
from wagtailmedia.models import Media

from wtrx.media_optimization import build_optimized_thumbnail, optimize_media_thumbnail

_SIGNAL_DISPATCH_UID = "wtrx.media_optimization.optimize_media_thumbnail"


class Command(BaseCommand):
    help = "Resize/recompress existing video thumbnails that predate automatic optimization on upload."

    def add_arguments(self, parser):
        parser.add_argument(
            "--media-id",
            type=int,
            default=None,
            help="Only process this single Media ID.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        media_items = Media.objects.exclude(thumbnail="").order_by("pk")
        if options["media_id"] is not None:
            media_items = media_items.filter(pk=options["media_id"])
        dry_run = options["dry_run"]

        if not dry_run:
            pre_save.disconnect(optimize_media_thumbnail, sender=Media, dispatch_uid=_SIGNAL_DISPATCH_UID)
        try:
            checked, updated, unreadable, failed = self._process(media_items, dry_run)
        finally:
            if not dry_run:
                pre_save.connect(optimize_media_thumbnail, sender=Media, dispatch_uid=_SIGNAL_DISPATCH_UID)

        self.stdout.write(self.style.SUCCESS(
            "\nChecked %d Media item(s), %s %d, %d unreadable, %d failed."
            % (
                checked,
                "would update" if dry_run else "updated",
                updated,
                unreadable,
                failed,
            )
        ))

    def _process(self, media_items, dry_run):
        checked = updated = unreadable = failed = 0
        for media in media_items:
            checked += 1
            original_name = media.thumbnail.name
            try:
                original_size = media.thumbnail.size
            except Exception as exc:  # noqa: BLE001 -- report and keep going
                self.stderr.write(self.style.WARNING(f"  FAILED (read): {media.pk} {original_name} — {exc}"))
                failed += 1
                continue

            try:
                optimized = build_optimized_thumbnail(media.thumbnail)
            except Exception as exc:  # noqa: BLE001 -- report and keep going
                self.stderr.write(self.style.WARNING(f"  FAILED (process): {media.pk} {original_name} — {exc}"))
                failed += 1
                continue

            if optimized is None:
                self.stdout.write(f"  skip (not a decodable image): {media.pk} {original_name}")
                unreadable += 1
                continue

            new_size = len(optimized.read())
            optimized.seek(0)

            if dry_run:
                self.stdout.write(
                    f"  [dry-run] {media.pk} {original_name}: {original_size} -> ~{new_size} bytes"
                )
                updated += 1
                continue

            media.thumbnail = optimized
            media.save(update_fields=["thumbnail"])
            self.stdout.write(f"  updated: {media.pk} {original_name}: {original_size} -> {new_size} bytes")
            updated += 1

        return checked, updated, unreadable, failed

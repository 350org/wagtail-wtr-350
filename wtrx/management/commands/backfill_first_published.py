"""
Give published pages a `first_published_at` where the import never set one.

Content brought over from WordPress (see import_350_blog / import_350_press_releases)
arrives live but with `first_published_at` empty -- Wagtail only sets that field
when a page is published through the admin. Anything that orders by it is then
sorting on mostly-NULL data, and PostgreSQL sorts NULLs *first* under `DESC`, so
the handful of pages that do have a real date sink to the bottom.

The visible symptom: PageCardsBlock ("the 3 most recently published pages under
this index page") never shows a genuinely new post, because every imported page
outranks it.

`published_at` on Post is the editor-controlled publication date and is the
right value to backfill from; `latest_revision_created_at` is the fallback for
page types that have no `published_at`.

    python manage.py backfill_first_published --dry-run
    python manage.py backfill_first_published

Idempotent: pages that already have a `first_published_at` are left alone.
"""

from django.core.management.base import BaseCommand

from wagtail.models import Page


class Command(BaseCommand):
    help = "Set first_published_at on live pages that are missing it."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing.",
        )

    def handle(self, *args, **options):
        missing = Page.objects.live().filter(first_published_at=None).specific()
        updated, skipped = 0, []

        for page in missing:
            stamp = (
                getattr(page, "published_at", None)
                or page.latest_revision_created_at
            )
            if stamp is None:
                skipped.append(page)
                continue
            self.stdout.write(
                "  %-6s %-52s <- %s" % (page.pk, page.title[:52], stamp)
            )
            if not options["dry_run"]:
                # update() rather than save(): this is a data correction, and
                # saving a Page would touch revisions and fire publish signals.
                Page.objects.filter(pk=page.pk).update(first_published_at=stamp)
            updated += 1

        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    "\nNo date available for %d page(s): %s"
                    % (len(skipped), ", ".join(str(p.pk) for p in skipped))
                )
            )
        verb = "Would update" if options["dry_run"] else "Updated"
        self.stdout.write(self.style.SUCCESS("\n%s %d page(s)." % (verb, updated)))

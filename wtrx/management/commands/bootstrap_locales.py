"""
Create a `Locale` row for every language in `WAGTAIL_CONTENT_LANGUAGES`.

Locale rows are what make a language usable for content -- the settings entry
alone only makes it *offerable*. Wagtail's own Settings > Locales screen creates
them one at a time, and its create view 403s once every configured language
already has a row, which makes "did this environment get all of them?" awkward
to answer by clicking. This does the whole list at once, so a fresh database
(local, review app, a restored dump) reaches the same state as production with
one command.

    python manage.py bootstrap_locales --dry-run
    python manage.py bootstrap_locales

Idempotent: languages that already have a row are left untouched. It never
deletes a Locale -- `Locale` FKs are `on_delete=PROTECT`, so removing one that
pages already use is a deliberate act for a human, not a side effect of running
a bootstrap command after someone edited the settings list.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from wagtail.models import Locale


class Command(BaseCommand):
    help = "Create Locale rows for every language in WAGTAIL_CONTENT_LANGUAGES."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be created without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        configured = [code for code, _label in settings.WAGTAIL_CONTENT_LANGUAGES]
        existing = set(Locale.objects.values_list("language_code", flat=True))

        created = []
        for code in configured:
            if code in existing:
                continue
            if not dry_run:
                Locale.objects.create(language_code=code)
            created.append(code)

        for code in created:
            verb = "Would create" if dry_run else "Created"
            self.stdout.write(f"{verb} locale: {code}")

        unconfigured = sorted(existing - set(configured))
        if unconfigured:
            self.stdout.write(
                self.style.WARNING(
                    "Locale rows with no matching WAGTAIL_CONTENT_LANGUAGES entry "
                    f"(left alone): {', '.join(unconfigured)}"
                )
            )

        summary = f"{len(created)} created, {len(configured) - len(created)} already present."
        self.stdout.write(self.style.SUCCESS(f"Done. {summary}"))

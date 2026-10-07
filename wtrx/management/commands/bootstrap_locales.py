"""
Create the `Locale` rows an environment actually uses.

`WAGTAIL_CONTENT_LANGUAGES` lists every language any 350 site might need, so
that it can be picked in the admin. Only a few of those are real content at any
one time, and a `Locale` row is what makes one real -- so this command names the
languages to create rather than creating all of them. A stray row is not
harmless: it appears in every "translate into" menu, and `Locale` FKs are
`on_delete=PROTECT`, so once a page uses it, it cannot be removed again.

    python manage.py bootstrap_locales                      # report, writes nothing
    python manage.py bootstrap_locales en pt-br fr-fr
    python manage.py bootstrap_locales en pt-br --dry-run
    python manage.py bootstrap_locales --all                # every configured language

Idempotent: a language that already has a row is left untouched, and a row is
never deleted.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from wagtail.models import Locale


class Command(BaseCommand):
    help = "Create Locale rows for the given languages (or report what exists)."

    def add_arguments(self, parser):
        parser.add_argument(
            "language_codes",
            nargs="*",
            help="Languages to create, e.g. en pt-br fr-fr. Omit to report only.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Create a row for every language in WAGTAIL_CONTENT_LANGUAGES.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be created without writing.",
        )

    def handle(self, *args, **options):
        configured = [code for code, _label in settings.WAGTAIL_CONTENT_LANGUAGES]
        existing = set(Locale.objects.values_list("language_code", flat=True))

        requested = options["language_codes"]
        if options["all"]:
            if requested:
                raise CommandError("Give either language codes or --all, not both.")
            requested = configured

        unknown = [code for code in requested if code not in configured]
        if unknown:
            raise CommandError(
                f"Not in WAGTAIL_CONTENT_LANGUAGES: {', '.join(unknown)}. "
                "Add the language to settings first (that part is a deploy)."
            )

        if not requested:
            self._report(configured, existing)
            return

        dry_run = options["dry_run"]
        created = []
        for code in requested:
            if code in existing:
                continue
            if not dry_run:
                Locale.objects.create(language_code=code)
            created.append(code)

        for code in created:
            self.stdout.write(f"{'Would create' if dry_run else 'Created'} locale: {code}")

        unconfigured = sorted(existing - set(configured))
        if unconfigured:
            self.stdout.write(
                self.style.WARNING(
                    "Locale rows with no matching WAGTAIL_CONTENT_LANGUAGES entry "
                    f"(left alone): {', '.join(unconfigured)}"
                )
            )

        summary = f"{len(created)} created, {len(requested) - len(created)} already present."
        self.stdout.write(self.style.SUCCESS(f"Done. {summary}"))

    def _report(self, configured, existing):
        """No languages named: show what exists and what could be added."""
        self.stdout.write("Locales in this database:")
        for code in configured:
            if code in existing:
                self.stdout.write(f"  [x] {code}")
        self.stdout.write("\nAvailable but not created:")
        for code in configured:
            if code not in existing:
                self.stdout.write(f"  [ ] {code}")
        self.stdout.write(
            "\nName the ones to create, e.g. "
            "`manage.py bootstrap_locales pt-br fr-fr`, or pass --all."
        )

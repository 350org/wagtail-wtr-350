"""
Convert an existing English section into its own language tree.

The regional sections (`/brasil/`, `/france/`, `/indonesia/`) were built as
ordinary English subtrees under Home. Making one of them a real language site
means three things at once: the section root moves to Root level, every page in
it is retagged to the target locale, and the section root becomes the target
locale's counterpart of the site's root page -- which is what gives the tree a
URL at all (`Site.get_site_root_paths()` walks `root_page.get_translations()`,
so a language tree whose root is not a translation of the site root is
unreachable, with `page.url` returning None).

None of that is doable in the admin. `Page.locale` is `editable=False`, so no
form exposes it, and `Page.can_move_to()` refuses any parent whose locale
differs from the page's own -- with a deliberate carve-out for Root, which is
what makes the move half of this possible at all.

    python manage.py convert_section_to_locale 59 pt --dry-run
    python manage.py convert_section_to_locale 59 pt

This is NOT wagtail-localize's "Translate this page". That copies a page into
another locale and leaves the original in place, which is right for translating
`/about/` into Spanish and wrong here: these pages are already the Brazilian
site, not a translation of anything. Nothing is duplicated and no
TranslationSource is created.

Whether any URL changes depends on `WTRX_LANGUAGE_URL_PREFIXES`: a section
whose slug already matches its language's mapped prefix (`/brasil/` for pt)
keeps every URL it had and needs no redirects at all -- the conversion is
invisible from outside. Where a URL does move, a permanent redirect is created
per page. Wagtail's own `autocreate_redirects_on_page_move` cannot do that
here: it runs during the move, at which point the page is still in the old
locale and sitting at Root, where no site root path covers it -- its "new" URL
is None and nothing usable gets recorded. The redirects are therefore built
afterwards, from URLs captured before the first write, and skipped for any page
whose URL is unchanged.
"""

import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from wagtail.contrib.redirects.models import Redirect
from wagtail.models import Locale, Page, Revision, Site


class Command(BaseCommand):
    help = "Move a section to Root and retag it (and its descendants) to a locale."

    def add_arguments(self, parser):
        parser.add_argument("page_id", type=int, help="ID of the section's root page.")
        parser.add_argument("language_code", help="Target language, e.g. 'pt'.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing.",
        )
        parser.add_argument(
            "--no-redirects",
            action="store_true",
            help="Skip creating redirects from the section's old URLs.",
        )
        parser.add_argument(
            "--standalone",
            action="store_true",
            help=(
                "Give the section root a fresh translation_key instead of the site "
                "root's. The tree will have no URL until it is linked some other "
                "way -- only useful for a section that is not meant to be served."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        page = Page.objects.filter(id=options["page_id"]).first()
        if page is None:
            raise CommandError(f"No page with id {options['page_id']}.")

        locale = Locale.objects.filter(language_code=options["language_code"]).first()
        if locale is None:
            raise CommandError(
                f"No Locale for '{options['language_code']}'. Run `manage.py bootstrap_locales` first."
            )

        site = Site.objects.filter(is_default_site=True).first()
        if site is None:
            raise CommandError("No default Site.")
        site_root = site.root_page
        if page.pk == site_root.pk:
            raise CommandError("Refusing to convert the site's own root page.")

        link_to_site_root = not options["standalone"]
        if link_to_site_root:
            # unique_together("translation_key", "locale"): the site root can have
            # only one counterpart per language.
            clash = (
                Page.objects.filter(
                    translation_key=site_root.translation_key, locale=locale
                )
                .exclude(pk=page.pk)
                .first()
            )
            if clash is not None:
                raise CommandError(
                    f"'{locale.language_code}' already has a counterpart of the site root: "
                    f"{clash.title!r} (id {clash.pk}). Delete or convert that first."
                )

        pages = list(page.get_descendants(inclusive=True))
        already_at_root = page.depth == 2
        # Captured before any write: once the move lands, the old URLs are gone.
        old_urls = {target.pk: target.url for target in pages}

        self.stdout.write(f"Section     : {page.title!r} (id {page.pk}, {page.url_path})")
        self.stdout.write(f"Pages       : {len(pages)} ({len(pages) - 1} descendants)")
        self.stdout.write(f"Locale      : {page.locale.language_code} -> {locale.language_code}")
        self.stdout.write(
            "Move        : " + ("already at Root level" if already_at_root else "to Root level")
        )
        self.stdout.write(
            "Serves as   : "
            + (
                f"the {locale.language_code} counterpart of {site_root.title!r} -> /{locale.language_code}/"
                if link_to_site_root
                else "standalone (no URL until linked)"
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run — nothing written."))
            return

        with transaction.atomic():
            if not already_at_root:
                # Permitted only because the destination is Root: can_move_to()
                # rejects every other parent whose locale differs from the page's.
                root = Page.objects.get(depth=1)
                page.move(root, pos="last-child")
                page.refresh_from_db()
                pages = list(page.get_descendants(inclusive=True))

            for target in pages:
                target.locale = locale
                # Descendants are this language's own pages, not translations of
                # their English equivalents, so each gets an identity of its own.
                # The section root is the exception when it becomes the site
                # root's counterpart -- that shared key is the linkage.
                if target.pk == page.pk and link_to_site_root:
                    target.translation_key = site_root.translation_key
                else:
                    target.translation_key = uuid.uuid4()

            Page.objects.bulk_update(pages, ["locale", "translation_key"])

            revisions = self._retag_revisions(pages, locale)

            # Root paths are cached for an hour and are what maps this tree to a URL.
            Site.clear_site_root_paths_cache()

            redirects = 0
            if not options["no_redirects"]:
                redirects = self._create_redirects(pages, old_urls, site)

        page.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(
                f"\nConverted {len(pages)} pages and {revisions} revisions, "
                f"created {redirects} redirects. "
                f"Section now serves at {page.url or '(no URL)'}"
            )
        )

    def _create_redirects(self, pages, old_urls, site):
        """Permanent redirects from each page's pre-conversion URL to the page."""
        existing = set(
            Redirect.objects.filter(site=site).values_list("old_path", flat=True)
        )
        redirects = []
        for page in pages:
            # No refresh needed: bulk_update has just written these instances,
            # and url_path came from the post-move re-fetch.
            old_url = old_urls.get(page.pk)
            if not old_url or old_url == page.url:
                continue
            old_path = Redirect.normalise_path(old_url)
            if old_path in existing:
                continue
            existing.add(old_path)
            redirects.append(
                Redirect(
                    old_path=old_path,
                    site=site,
                    redirect_page=page,
                    is_permanent=True,
                    automatically_created=True,
                )
            )
        Redirect.objects.bulk_create(redirects, batch_size=500)
        return len(redirects)

    def _retag_revisions(self, pages, locale):
        """
        Rewrite `locale` and `translation_key` inside stored revision content.

        A revision holds its own copy of the page's fields. Without this, the
        first editor to revert an old revision silently puts that page back in
        the previous locale -- a failure that surfaces days later, on one page,
        with nothing connecting it to this command.
        """
        by_id = {str(page.pk): page for page in pages}
        page_type = Revision.objects.filter(
            base_content_type__app_label="wagtailcore", base_content_type__model="page"
        )
        revisions = list(page_type.filter(object_id__in=by_id.keys()))

        for revision in revisions:
            page = by_id[revision.object_id]
            content = revision.content
            content["locale"] = locale.pk
            content["translation_key"] = str(page.translation_key)
            revision.content = content

        Revision.objects.bulk_update(revisions, ["content"], batch_size=500)
        return len(revisions)

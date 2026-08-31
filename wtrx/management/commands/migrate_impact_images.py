"""
migrate_impact_images management command.

Two static HTML-to-HTML rewrites on the "Our Impact" page's raw_html
StreamField content (nested inside a `section` block's content list — see
AGENTS.md pitfalls #46/#48 on why the walker below never assumes a
particular block-nesting shape). This page is intentionally staying a raw
embed, not becoming an admin-editable block-built page, so both rewrites
work at the level of HTML strings, not StreamField block values:

1. IMAGE URLS: every <img src="..."> pointing at 350.org's own WordPress
   media library (https://350.org/wp-content/uploads/...) is downloaded and
   turned into a real wtrx.CustomImage on this project's own storage, then
   the src is rewritten to point at it. Reuses download_image() from
   _wp_content_utils.py — the same helper import_350_blog.py already uses
   against this exact domain (WordPress "-WIDTHxHEIGHT" scaled-image
   upgrade, per-URL failure handling that doesn't abort the whole run).

2. "EXPANDOS": the page's <ul class="victories"> lists (custom
   expando-link/expando-inner collapsible items — 350.org's own bespoke
   component, unrelated to Wagtail) are replaced with the exact static HTML
   wtrx/templates/wtrx/components/streamfield/blocks/accordion_block.html
   renders for equivalent content. static_src/js/main.js calls
   Accordion.init() on every page load, which scans the whole document for
   [data-accordion] — so this markup gets real expand/collapse behavior,
   ARIA wiring and site styling for free, with no JS of its own and no need
   for this to be a real AccordionBlock. That distinction is what saves this
   step from AccordionItemBlock's real limitation: it's a plain
   RichTextBlock with no image/embed feature enabled, so a genuine block
   conversion would lose the image or video every "victory" item carries
   (measured against the real page: 83 items, only 1 text-only, 67 with an
   image, 15 with a video). A hardcoded HTML string has no such
   restriction, so each item's body — text, image, or video-container
   iframe — is carried over exactly as it was.

Order matters: image URLs are rewritten first, across the whole raw_html
string (including inside soon-to-be-converted victories items), so the
accordion conversion step copies over already-fixed <img src> values.

Safe by default: writes a new page revision, does NOT publish it. Pass
--publish to publish immediately instead — see that flag's help text.

Usage:
    # Always dry-run first -- prints every match with no downloads/writes.
    python manage.py migrate_impact_images --old-domain https://350.org --dry-run

    # Real run: downloads images, creates CustomImage records, converts
    # expandos to accordion markup, saves a draft revision.
    python manage.py migrate_impact_images --old-domain https://350.org

    # Real run that also publishes immediately.
    python manage.py migrate_impact_images --old-domain https://350.org --publish
"""

import re

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError

from wtrx.management.commands._wp_content_utils import download_image

_IMG_SRC_RE = re.compile(r'<img\b[^>]*\bsrc=["\']([^"\']+)["\']', re.IGNORECASE)

_ACCORDION_ITEM_TEMPLATE = """        <div class="accordion-item overflow-hidden rounded-lg border-2 border-neutral-200 bg-neutral-50">
            <button type="button" class="flex w-full items-center justify-between gap-4 px-8 py-6 text-left font-body text-lg leading-[1.429] text-dark transition-colors hover:bg-neutral-200/50 sm:text-xl" aria-expanded="false" data-accordion-toggle>
                <span>{title}</span>
                <svg class="h-5 w-5 shrink-0 opacity-60 transition-transform duration-200" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
            </button>
            <div class="hidden bg-white px-8 pt-6 pb-6 prose prose-neutral max-w-none text-lg sm:text-xl [&>:first-child>:first-child]:mt-0 [&>:last-child>:last-child]:mb-0" data-accordion-content>
                {content}
            </div>
        </div>"""


def _is_old_url(url, old_domain, extra_urls):
    """
    True if ``url`` should be treated as a legacy reference to migrate:
    either it starts with ``old_domain`` (when supplied) or it's explicitly
    listed in ``extra_urls`` (from --url-list). Never matches a URL already
    pointing at this project's own storage.
    """
    if not url or not url.startswith(("http://", "https://")):
        return False
    if url in extra_urls:
        return True
    if old_domain and url.startswith(old_domain):
        return True
    return False


def rewrite_image_urls(html, old_domain, extra_urls, session, stdout, dry_run=False):
    """
    Replace every <img src="..."> in ``html`` matching old_domain/extra_urls
    with a real CustomImage's URL, downloading/creating it via
    download_image() as needed (which already dedupes by filename across
    calls, so re-running this is safe). Returns (new_html, resolved, failed).
    """
    resolved = 0
    failed = 0
    urls = sorted(set(_IMG_SRC_RE.findall(html)))
    for url in urls:
        if not _is_old_url(url, old_domain, extra_urls):
            continue
        image = download_image(session, url, stdout, dry_run=dry_run)
        if image is None:
            if not dry_run:
                failed += 1
                stdout.write(f"    FAILED to resolve image: {url}")
            continue
        resolved += 1
        if not dry_run:
            html = html.replace(f'src="{url}"', f'src="{image.file.url}"')
            html = html.replace(f"src='{url}'", f"src='{image.file.url}'")
    return html, resolved, failed


def _victories_ul_to_accordion_html(ul_tag):
    """
    Build the accordion_block.html-equivalent static markup for one
    <ul class="victories"> list, or None if it has no recognizable items.

    Each <li>'s .expando-link text becomes the accordion item's title;
    its .expando-inner's full inner HTML (text, image, video-container —
    whatever it holds) becomes the answer panel's content, unchanged. The
    old list's "reverse-order"/"single-col" alternating-layout classes are
    deliberately dropped — the point of this conversion is the site's
    standard flat accordion look, not preserving the bespoke old layout.
    """
    items_html = []
    for li in ul_tag.find_all("li", recursive=False):
        link = li.find("a", class_="expando-link")
        inner = li.find("div", class_="expando-inner")
        if link is None or inner is None:
            continue
        title = link.get_text(strip=True)
        content = inner.decode_contents().strip()
        items_html.append(_ACCORDION_ITEM_TEMPLATE.format(title=title, content=content))
    if not items_html:
        return None
    return (
        '<div class="wtr-accordion flex flex-col gap-4" data-accordion>\n'
        + "\n".join(items_html)
        + "\n</div>"
    )


def convert_expandos_to_accordions(html, stdout):
    """
    Replace every <ul class="victories"> list in ``html`` with the static
    HTML our real AccordionBlock component renders for equivalent content —
    see accordion_block.html and this module's docstring for why a
    hardcoded HTML string, not a real StreamField block, is the right
    target here. Returns (new_html, num_converted).

    Verifies BeautifulSoup's re-serialization of each matched <ul> is found
    verbatim in the original string before replacing it — if reserialization
    ever diverges from the source byte-for-byte (e.g. an unusual quoting or
    self-closing style BS4 normalizes), that <ul> is reported and left
    untouched rather than silently doing nothing, per AGENTS.md pitfalls
    #46/#48's lesson about migrations that appear to succeed while quietly
    changing nothing.
    """
    soup = BeautifulSoup(html, "html.parser")
    converted = 0
    for ul in soup.find_all("ul", class_="victories"):
        original = str(ul)
        if original not in html:
            stdout.write(
                "    WARNING: could not locate exact source text for a victories "
                f"<ul> -- leaving it unconverted: {original[:80]}..."
            )
            continue
        new_html = _victories_ul_to_accordion_html(ul)
        if new_html is None:
            stdout.write("    WARNING: a victories <ul> had no recognizable items -- leaving it unconverted")
            continue
        html = html.replace(original, new_html, 1)
        converted += 1
    return html, converted


def _iter_string_leaves(node):
    """
    Recursively yield (container, key) for every string leaf in a raw
    StreamField JSON tree, where ``container[key]`` is that string.
    Callers mutate ``container[key]`` in place to rewrite content.

    Walks generically rather than assuming a particular block-nesting shape
    (StructBlock value, ListBlock item wrapper, etc.) — see AGENTS.md
    pitfalls #46/#48.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                yield from _iter_string_leaves(value)
            elif isinstance(value, str):
                yield node, key
    elif isinstance(node, list):
        for i, value in enumerate(node):
            if isinstance(value, (dict, list)):
                yield from _iter_string_leaves(value)
            elif isinstance(value, str):
                yield node, i


class Command(BaseCommand):
    help = (
        "Rewrite legacy <img src> references and 'expando' collapsible lists on a "
        "raw-HTML page (default: the 'Our Impact' page) to point at real CustomImage "
        "uploads and this site's own accordion markup, respectively."
    )

    def add_arguments(self, parser):
        parser.add_argument("--page-id", type=int, help="Page ID to migrate. Overrides --slug.")
        parser.add_argument(
            "--slug",
            default="our-impact",
            help="Slug of the page to migrate if --page-id is not given (default: our-impact).",
        )
        parser.add_argument(
            "--fields",
            default="body",
            help="Comma-separated list of StreamField attribute names on the page to scan "
            "(default: body).",
        )
        parser.add_argument(
            "--old-domain",
            default="",
            help="Base URL of the old image source, e.g. https://350.org -- any <img src> "
            "starting with this is downloaded and rewritten. Required unless --url-list is "
            "given. Expando-to-accordion conversion always runs regardless of this option.",
        )
        parser.add_argument(
            "--url-list",
            help="Path to a newline-delimited file of exact legacy image URLs to migrate, for "
            "cases where a domain prefix is too broad or too narrow. Can be combined with "
            "--old-domain.",
        )
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Publish the new revision immediately. Without this flag, a draft revision is "
            "saved and the live page is left unchanged until someone reviews and publishes it "
            "in the admin -- the safer default for a script meant to run against production.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be downloaded and rewritten without writing to the DB or "
            "storage backend. Always run this first.",
        )

    def handle(self, *args, **options):
        import requests

        from wagtail.models import Page

        old_domain = options["old_domain"]
        url_list_path = options["url_list"]
        if not old_domain and not url_list_path:
            raise CommandError("Supply --old-domain and/or --url-list identifying the legacy image source.")

        extra_urls = set()
        if url_list_path:
            with open(url_list_path) as f:
                extra_urls = {line.strip() for line in f if line.strip()}

        if options["page_id"]:
            page = Page.objects.filter(pk=options["page_id"]).first()
        else:
            page = Page.objects.filter(slug=options["slug"]).first()
        if page is None:
            raise CommandError(
                f"No page found (page_id={options['page_id']!r}, slug={options['slug']!r})."
            )
        page = page.specific

        dry_run = options["dry_run"]
        session = requests.Session()

        total_images_resolved = 0
        total_images_failed = 0
        total_accordions_converted = 0
        any_field_changed = False

        for field_name in [f.strip() for f in options["fields"].split(",")]:
            stream_value = getattr(page, field_name, None)
            if stream_value is None:
                self.stderr.write(self.style.WARNING(f"Page has no field '{field_name}', skipping."))
                continue

            raw_data = list(stream_value.raw_data)
            field_changed = False

            for container, key in _iter_string_leaves(raw_data):
                html = container[key]
                if "<img" not in html and "victories" not in html:
                    continue

                new_html, resolved, failed = rewrite_image_urls(
                    html, old_domain, extra_urls, session, self.stdout, dry_run=dry_run
                )
                new_html, converted = convert_expandos_to_accordions(new_html, self.stdout)

                total_images_resolved += resolved
                total_images_failed += failed
                total_accordions_converted += converted

                if resolved or converted:
                    self.stdout.write(
                        f"{field_name}: resolved {resolved} image(s), converted {converted} "
                        "expando list(s) in one HTML block"
                    )

                if not dry_run and new_html != html:
                    container[key] = new_html
                    field_changed = True

            if field_changed:
                setattr(page, field_name, raw_data)
                any_field_changed = True

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run complete. would-resolve-images={total_images_resolved} "
                    f"would-fail={total_images_failed} would-convert-accordions="
                    f"{total_accordions_converted}. Nothing written."
                )
            )
            return

        if not any_field_changed:
            self.stdout.write("No changes to save.")
            return

        revision = page.save_revision()
        if options["publish"]:
            revision.publish()
            self.stdout.write(self.style.SUCCESS(f"Saved and published a new revision of {page!r}."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Saved a new DRAFT revision of {page!r} (not published). Review it in the "
                    "admin and publish when ready, or re-run with --publish."
                )
            )

        self.stdout.write(
            f"Done. images_resolved={total_images_resolved} images_failed={total_images_failed} "
            f"accordions_converted={total_accordions_converted}"
        )

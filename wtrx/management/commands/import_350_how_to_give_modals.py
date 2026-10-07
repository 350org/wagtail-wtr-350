"""
import_350_how_to_give_modals management command.

Copies the "Ways to give" modals on 350.org's How to Give page into the
matching cards' ``modal`` field (CardBlock) on a Wagtail page.

On WordPress each card's button is ``<a class="js-modal" href="#daf">`` and
the modal bodies all sit in one hidden ``.modal-content`` container, one
``<div id="daf">`` per modal. The Wagtail page's cards were imported pointing
at those same anchors on 350.org (``link_url`` ending in ``#daf``), so the
pairing is by that fragment: each card whose link_url ends in ``#<id>`` gets
the ``<div id="<id>">`` body as modal content, and its link_url is cleared.

Body HTML is cleaned to RICHTEXT_FEATURES_FULL via the shared WordPress
importer helpers. ``<script>``/``<link>``/``<style>`` runs are kept verbatim
as a ``raw_html`` child instead — the Donor Advised Funds modal embeds the
DAFdirect widget that way (two scripts; dafdirect4.js document.writes its
form in place at parse time, which still works inside a server-rendered
<dialog>).

Saves a new draft revision by default so an editor can review it before it
goes live; ``--publish`` publishes it instead.

Usage:
    python manage.py import_350_how_to_give_modals --page take-action/how-to-give --dry-run
    python manage.py import_350_how_to_give_modals --page 123
    python manage.py import_350_how_to_give_modals --page 123 \\
        --source https://350.org/fr/comment-donner/
"""

import copy
import uuid
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from django.core.management.base import BaseCommand, CommandError
from wagtail.models import Page

from wtrx.management.commands._wp_content_utils import (
    _BLOCK_TAG_MAP,
    _TAG_FACTORY,
    _build_clean,
    _unmask_cf_emails,
)

USER_AGENT = "350-wagtail-blog-import/1.0 (+https://github.com/)"
DEFAULT_SOURCE_URL = "https://350.org/how-to-give/"
REQUEST_TIMEOUT = 30

# Kept verbatim as a raw_html child rather than stripped (the richtext
# cleaner drops all three along with their contents).
_EMBED_TAGS = {"script", "link", "style"}


def _rewrite_fundraiseup_link(a_tag):
    """
    Point a 350.org ``?form=FUN...`` link at this page instead.

    Fundraise Up opens its checkout for any ``?form=`` URL on a page that
    loads its installation script, so ``?form=X`` works on the Wagtail page
    as-is — but the absolute 350.org URL would bounce the visitor back to
    WordPress first.
    """
    href = a_tag.get("href", "")
    parsed = urlparse(href)
    if not parsed.netloc.endswith("350.org"):
        return
    form_ids = parse_qs(parsed.query).get("form")
    if form_ids:
        a_tag["href"] = f"?form={form_ids[0]}"


def _strip_trailing_breaks(tag):
    while tag.contents:
        last = tag.contents[-1]
        if isinstance(last, Tag) and last.name == "br":
            last.extract()
        elif isinstance(last, NavigableString) and not last.strip():
            last.extract()
        else:
            break


def convert_modal(modal_div):
    """
    Convert one modal ``<div>`` into CardModalContentBlock raw stream data.

    Walks top-level children, grouping cleaned richtext into ``text`` children
    and consecutive embed tags into ``raw_html`` children, preserving order.
    Inline content left bare by an unwrapped ``<div>`` (350.org's address
    blocks are ``<div class="padding-left-medium">`` holding text and
    ``<br>``s directly) is gathered into a ``<p>`` so it stays valid
    richtext.
    """
    _unmask_cf_emails(modal_div)
    # Cloudflare injects its own email-decode script next to any obfuscated
    # address; _unmask_cf_emails already decoded them, and /cdn-cgi/ doesn't
    # exist on our origin.
    for script in modal_div.find_all("script", src=True):
        if "/cdn-cgi/" in script["src"]:
            script.decompose()
    for a_tag in modal_div.find_all("a"):
        _rewrite_fundraiseup_link(a_tag)
    # 350.org's bold-paragraph utility class; the cleaner drops classes.
    for tag in modal_div.select(".text-strong"):
        strong = _TAG_FACTORY.new_tag("strong")
        for child in list(tag.children):
            strong.append(child.extract())
        tag.append(strong)

    children = []
    text_parts = []
    inline = []
    embed_parts = []

    def flush_inline():
        if not inline:
            return
        p = _TAG_FACTORY.new_tag("p")
        for node in inline:
            p.append(node)
        inline.clear()
        _strip_trailing_breaks(p)
        if p.get_text(strip=True):
            text_parts.append(str(p))

    def flush_text():
        flush_inline()
        if text_parts:
            children.append({"type": "text", "value": "".join(text_parts)})
            text_parts.clear()

    def flush_embed():
        if embed_parts:
            children.append({"type": "raw_html", "value": "\n".join(embed_parts)})
            embed_parts.clear()

    for node in modal_div.children:
        if isinstance(node, Comment):
            continue
        if isinstance(node, Tag) and node.name.lower() in _EMBED_TAGS:
            flush_text()
            embed_parts.append(str(node))
            continue
        if isinstance(node, NavigableString) and not node.strip():
            continue
        flush_embed()
        for cleaned in _build_clean(node):
            if isinstance(cleaned, Tag) and cleaned.name in _BLOCK_TAG_MAP.values():
                flush_inline()
                _strip_trailing_breaks(cleaned)
                if cleaned.get_text(strip=True):
                    text_parts.append(str(cleaned))
            elif isinstance(cleaned, NavigableString) and not cleaned.strip() and not inline:
                continue
            else:
                inline.append(cleaned)
    flush_text()
    flush_embed()

    for child in children:
        child["id"] = str(uuid.uuid4())
    return children


def _iter_cards(data):
    """Yield every card-shaped dict (has `content` and `link_url`) in raw stream data."""
    if isinstance(data, dict):
        if "content" in data and "link_url" in data:
            yield data
        for value in data.values():
            yield from _iter_cards(value)
    elif isinstance(data, list):
        for item in data:
            yield from _iter_cards(item)


def _resolve_page(ref):
    if ref.isdigit():
        page = Page.objects.filter(pk=int(ref)).first()
        if page is None:
            raise CommandError(f"No page with id {ref}.")
        return page.specific
    slug = ref.strip("/").split("/")[-1]
    matches = [p for p in Page.objects.filter(slug=slug) if p.url_path.rstrip("/").endswith("/" + ref.strip("/"))]
    if not matches:
        raise CommandError(f"No page found matching '{ref}'.")
    if len(matches) > 1:
        ids = ", ".join(f"{p.pk} ({p.url_path})" for p in matches)
        raise CommandError(f"'{ref}' matches more than one page: {ids}. Pass --page <id> instead.")
    return matches[0].specific


class Command(BaseCommand):
    help = "Import 350.org How to Give modals into the matching cards' modal content."

    def add_arguments(self, parser):
        parser.add_argument(
            "--page",
            required=True,
            help="Target Wagtail page: an id, or its path (e.g. take-action/how-to-give).",
        )
        parser.add_argument(
            "--source",
            default=DEFAULT_SOURCE_URL,
            help=f"350.org page to read the modals from (default {DEFAULT_SOURCE_URL}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without saving anything.",
        )
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Publish the new revision instead of leaving it as a draft.",
        )

    def handle(self, *args, **options):
        page = _resolve_page(options["page"])
        if not hasattr(page, "body"):
            raise CommandError(f"{page} has no body StreamField.")

        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
        try:
            response = session.get(options["source"], timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise CommandError(f"Could not fetch {options['source']}: {exc}") from exc

        soup = BeautifulSoup(response.text, "html.parser")
        container = soup.select_one(".modal-content.hidden") or soup.select_one(".modal-content")
        modal_divs = {div["id"]: div for div in container.find_all("div", id=True, recursive=False)} if container else {}
        if not modal_divs:
            raise CommandError(f"No modal content found on {options['source']}.")

        body = copy.deepcopy(list(page.body.raw_data))
        matched = set()
        for card in _iter_cards(body):
            fragment = urlparse(card.get("link_url") or "").fragment
            if fragment not in modal_divs:
                continue
            modal = convert_modal(copy.copy(modal_divs[fragment]))
            kinds = ", ".join(child["type"] for child in modal)
            self.stdout.write(f"  #{fragment}: {card.get('link_text') or '(no link text)'} -> {kinds}")
            card["modal"] = modal
            card["link_url"] = ""
            matched.add(fragment)

        for fragment in sorted(set(modal_divs) - matched):
            self.stdout.write(self.style.WARNING(f"  #{fragment}: no card links to it — skipped"))

        if not matched:
            self.stdout.write(self.style.WARNING("No cards matched; nothing to save."))
            return
        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Dry run: would update {len(matched)} card(s) on {page}."))
            return

        page.body = body
        revision = page.save_revision(log_action=True)
        if options["publish"]:
            revision.publish()
            self.stdout.write(self.style.SUCCESS(f"Published {len(matched)} modal(s) on {page}."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Saved {len(matched)} modal(s) on {page} as a draft revision.")
            )

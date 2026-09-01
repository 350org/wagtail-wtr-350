"""
import_350_our_impact management command.

Scrapes https://350.org/our-impact/ directly (not the WP REST API — this is
a bespoke timeline page, not a regular post type, same situation
import_350_press_releases.py is in) and populates a page's body with one
real TimelineBlock, replacing the raw-HTML-embed approach a now-removed
migrate_impact_images.py command used to work around (see AGENTS.md
pitfall #51, and commit ca0aea4/git history for that command's own
docstring if its original design is ever needed again).

Source structure (confirmed against the live page, not guessed):

    <div class="timeline-container">
      <section class="year" id="year-2011">
        <h2>2011</h2>
        <div class="year-content">
          <p class="intro title4">Resisting the Keystone XL Pipeline</p>
          <div class="year-text"><p>...intro copy...</p></div>
          <img src="..." alt="...">                          <!-- optional, some years -->
          <div class="embed-section"><div class="video-container">
              <iframe src="...">                              <!-- optional, some years -->
          </div></div>
          <h3 class="victories-header">Our Victories at a Glance</h3>  <!-- optional -->
          <ul class="victories">
            <li>
              <a class="expando-link">Title</a>
              <div class="expando-inner">
                <div class="victory-text"><p>...</p></div>
                <img src="..." alt="...">                     <!-- most items -->
                <div class="video-container"><iframe src="..."></div>  <!-- some items -->
              </div>
            </li>
            ...
          </ul>
        </div>
      </section>
      ...
    </div>

Field mapping, per year:
    <p class="intro title4"> + <div class="year-text">  -> one "text" block,
        the title folded in as a real <h2> ahead of the copy (no separate
        heading field on TimelineYearBlock -- AGENTS.md pitfall #46's
        condensed-heading convention).
    direct <img>                                         -> one "image" block.
    <div class="embed-section"> video                    -> one "video" block.
    <h3 class="victories-header"> + <ul class="victories"> -> the header's
        text as a small "text" block, then one "accordion" block: each <li>
        -> AccordionItemBlock (title from .expando-link, content from
        .victory-text cleaned to a single richtext string, plus the item's
        own image/video via the AccordionItemBlock fields added for exactly
        this — see wtrx/blocks/__init__.py and AGENTS.md).

Known, deliberately accepted gaps (all logged as warnings, never abort the
run — same per-item failure tolerance as download_image()/rewrite_image_urls()):
  - A victory item's video is only imported when Wagtail's own OEmbedFinder
    recognises the provider (checked locally via `.accept()`, no network
    call) -- YouTube and Vimeo do; the one item on the live page hosted on
    350's own 350org.widen.net CDN does not, and is left without a video.
  - A handful of victory items with >1 image import only the first
    (AccordionItemBlock.image is a single ImageBlock, same one-value-per-field
    convention as every other block in this codebase).
  - The one item embedding a tweet (<div class="twitter-container">, not an
    <img> or <video-container>) keeps its text but the tweet itself is
    dropped -- not worth a one-off Twitter-oEmbed integration for a single
    item.
  - A handful of source <img alt="..."> values contain unescaped literal
    quote characters (a real markup bug on 350.org's own page, confirmed by
    inspecting the raw HTML directly -- not a parsing bug here), which can
    shift html.parser's attribute boundary detection for whatever tag
    follows and leave a stray trailing punctuation character on that next
    image's imported title. Cosmetic only (the title field, not the file
    itself), and caught during a real run as a couple of odd-looking
    filenames in the "downloaded image" log lines -- worth a quick glance
    at Settings > Images after an import, not worth a bespoke HTML repair
    pass for a source page that isn't ours to fix.

Usage:
    # Always dry-run first -- prints the years/items found, no writes.
    python manage.py import_350_our_impact --dry-run

    # Real run against the existing page (matched by --slug, default
    # 'our-impact'). Saves a draft revision only.
    python manage.py import_350_our_impact --update

    # ...and publish immediately.
    python manage.py import_350_our_impact --update --publish

    # Parse a manually-saved copy of the page instead of fetching it live
    # (e.g. if the live fetch ever gets blocked -- see AGENTS.md).
    python manage.py import_350_our_impact --update --source-file our-impact.html
"""

import re
import uuid

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError

from wtrx.management.commands._wp_content_utils import _build_clean, download_image

SOURCE_URL = "https://350.org/our-impact/"
USER_AGENT = "350-wagtail-our-impact-import/1.0 (+https://github.com/)"

_DEFAULT_VICTORIES_LABEL = "Our Victories at a Glance"

_YOUTUBE_EMBED_RE = re.compile(
    r"^https?://(?:www\.)?youtube(?:-nocookie)?\.com/embed/([A-Za-z0-9_-]+)"
)


def _normalize_video_url(url):
    """
    Rewrite a YouTube iframe /embed/<id> src (both youtube.com and the
    youtube-nocookie.com privacy-enhanced domain -- confirmed both appear on
    the live page) to the canonical /watch?v=<id> form.

    Wagtail's default OEmbedFinder provider regex matches the canonical
    watch/share URL, not the raw /embed/ src an <iframe> actually uses --
    confirmed directly: .accept() returns False for the /embed/ form and
    True for /watch?v=. Vimeo's player.vimeo.com/video/<id> embed src is
    already accepted as-is, so it needs no equivalent rewrite.
    """
    match = _YOUTUBE_EMBED_RE.match(url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    return url


def _safe_download_image(session, url, stdout, dry_run):
    """
    Wrap download_image() with a broad except -- unlike migrate_impact_images.py
    and the two existing importers (which only ever fetch images from
    350.org's own WordPress uploads), this page's images come from a dozen+
    third-party domains (350org.widen.net, cloudfront, media1.fdncms.com,
    globalpowerup.org, ...), and one of those returned content Willow
    couldn't decode as an image at all (a bare ElementTree.ParseError while
    probing for SVG) -- not a network failure, so download_image()'s own
    requests.exceptions.RequestException handling doesn't catch it. A single
    bad image shouldn't abort an import of 80+ items, so this is caught here
    rather than widening the shared helper's contract for every caller.
    """
    try:
        return download_image(session, url, stdout, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, see docstring
        stdout.write(f"    WARNING: failed to process image {url} — {exc!r}")
        return None


def _stream_block(block_type, value):
    """Build one StreamField entry with a stable UUID (matches create_test_page.py's _sb)."""
    return {"type": block_type, "value": value, "id": str(uuid.uuid4())}


_YEAR_ANCHOR_HREF_RE = re.compile(r'href="#year-(\d+)"')


def _clean_fragment(node):
    """
    Clean every child of ``node`` via _wp_content_utils._build_clean() and
    join the result into a single richtext-safe HTML string.

    Unlike convert_body()/_process_nodes(), which split content into
    multiple top-level typed blocks, this always produces one continuous
    string -- what a single richtext field (AccordionItemBlock.content, or
    a "text" StreamField block) needs.

    Several victory items link to another year in-page (e.g. "Scroll down to
    2021, when..."), as <a href="#year-2021">. _build_clean() preserves any
    href verbatim (correct for a real external link), so those in-page
    fragment links need rewriting to match TimelineBlock's own anchor
    scheme (id="timeline-year-2021", not "year-2021") or they'd silently do
    nothing -- confirmed by rendering a real imported page and clicking one.
    """
    cleaned = []
    for child in node.children:
        cleaned.extend(_build_clean(child))
    html = "".join(str(n) for n in cleaned).strip()
    return _YEAR_ANCHOR_HREF_RE.sub(r'href="#timeline-year-\1"', html)


def _embed_url_if_supported(container, stdout, context):
    """
    Return the first <iframe src> inside ``container`` if Wagtail's own
    OEmbedFinder recognises the provider (a pure local regex match against
    the provider list -- no network call), else None (with a warning).

    Skips rather than guesses: a URL Wagtail can't resolve would render
    nothing via {% embed %} anyway (video_block.html/accordion_block.html
    both branch on embed_url being set), so setting it here would just
    produce a silently-empty video block later.
    """
    from wagtail.embeds.finders.oembed import OEmbedFinder

    iframe = container.find("iframe")
    if iframe is None or not iframe.get("src"):
        return None
    src = _normalize_video_url(iframe["src"])
    if OEmbedFinder().accept(src):
        return src
    stdout.write(f"    WARNING: unsupported video provider for {context}, skipping video: {src}")
    return None


def _victory_item(li_tag, session, stdout, dry_run):
    """
    Build one AccordionItemBlock value from a <li> in <ul class="victories">,
    or None if it has no recognizable title/content (mirrors
    migrate_impact_images.py's _victories_ul_to_accordion_html tolerance).
    """
    link = li_tag.find("a", class_="expando-link")
    inner = li_tag.find("div", class_="expando-inner")
    if link is None or inner is None:
        return None
    title = link.get_text(strip=True)

    text_container = inner.find("div", class_="victory-text") or inner
    content = _clean_fragment(text_container)

    image_value = {"image": None, "alt_text": "", "caption": ""}
    img_tag = inner.find("img")
    if img_tag is not None and img_tag.get("src"):
        image = _safe_download_image(session, img_tag["src"], stdout, dry_run=dry_run)
        if image is not None:
            image_value = {"image": image.pk, "alt_text": img_tag.get("alt", ""), "caption": ""}

    video_value = {"embed_url": "", "media_file": None, "caption": ""}
    video_container = inner.find("div", class_="video-container")
    if video_container is not None:
        embed_url = _embed_url_if_supported(video_container, stdout, context=f"victory item {title!r}")
        if embed_url:
            video_value = {"embed_url": embed_url, "media_file": None, "caption": ""}

    return {
        "title": title,
        "content": content,
        "image": image_value,
        "video": video_value,
    }


def _victories_accordion_block(ul_tag, session, stdout, dry_run):
    """Build the "accordion" StreamField entry for one <ul class="victories">, or None."""
    items = []
    for li in ul_tag.find_all("li", recursive=False):
        item = _victory_item(li, session, stdout, dry_run=dry_run)
        if item is not None:
            items.append(item)
    if not items:
        return None
    return _stream_block("accordion", {"items": items})


def _year_content_blocks(year_content, session, stdout, dry_run):
    """
    Walk one year's <div class="year-content"> in document order, building
    the StreamField block list for TimelineYearBlock.content.

    Dispatches by tag/class rather than assuming a fixed position for any
    child, since not every year has every optional piece (direct <img>,
    embed-section video, victories list) -- confirmed by inspecting several
    real years, not assumed.
    """
    blocks = []
    pending_heading_html = ""

    children = year_content.find_all(recursive=False)
    for i, node in enumerate(children):
        classes = node.get("class") or []

        if node.name == "p" and "intro" in classes and "title4" in classes:
            # Folded into the next "text" block as a real <h2> -- no
            # separate heading field on TimelineYearBlock (pitfall #46).
            pending_heading_html = f"<h2>{node.get_text(strip=True)}</h2>"
            continue

        if node.name == "div" and "year-text" in classes:
            body_html = _clean_fragment(node)
            blocks.append(_stream_block("text", pending_heading_html + body_html))
            pending_heading_html = ""
            continue

        if node.name == "img":
            if pending_heading_html:
                # No year-text div showed up to carry it -- don't drop it.
                blocks.append(_stream_block("text", pending_heading_html))
                pending_heading_html = ""
            if node.get("src"):
                image = _safe_download_image(session, node["src"], stdout, dry_run=dry_run)
                if image is not None:
                    blocks.append(
                        _stream_block(
                            "image", {"image": image.pk, "alt_text": node.get("alt", ""), "caption": ""}
                        )
                    )
            continue

        if node.name == "div" and "embed-section" in classes:
            embed_url = _embed_url_if_supported(node, stdout, context="year video")
            if embed_url:
                blocks.append(
                    _stream_block("video", {"embed_url": embed_url, "media_file": None, "caption": ""})
                )
            continue

        if node.name == "h3" and "victories-header" in classes:
            # Handled together with the <ul class="victories"> that follows.
            continue

        if node.name == "ul" and "victories" in classes:
            header = node.find_previous_sibling("h3", class_="victories-header")
            label = header.get_text(strip=True) if header is not None else _DEFAULT_VICTORIES_LABEL
            blocks.append(_stream_block("text", f"<h3>{label}</h3>"))
            accordion = _victories_accordion_block(node, session, stdout, dry_run=dry_run)
            if accordion is not None:
                blocks.append(accordion)
            continue

        stdout.write(f"    WARNING: unrecognized year-content element <{node.name} class={classes}>, skipping")

    if pending_heading_html:
        blocks.append(_stream_block("text", pending_heading_html))

    return blocks


def fetch_our_impact_html(session):
    resp = session.get(SOURCE_URL, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_years(html, session, stdout, dry_run):
    """Return the list of {"year": ..., "content": [...]} dicts for TimelineBlock.years."""
    soup = BeautifulSoup(html, "html.parser")
    years = []
    for section in soup.select("div.timeline-container > section.year"):
        h2 = section.find("h2")
        year = h2.get_text(strip=True) if h2 is not None else section.get("id", "").removeprefix("year-")
        if not year:
            stdout.write("    WARNING: a year section has no recognizable year, skipping")
            continue
        year_content = section.find("div", class_="year-content")
        if year_content is None:
            stdout.write(f"    WARNING: year {year} has no .year-content, skipping")
            continue
        content_blocks = _year_content_blocks(year_content, session, stdout, dry_run=dry_run)
        years.append({"year": year, "content": content_blocks})
    return years


class Command(BaseCommand):
    help = "Import https://350.org/our-impact/ as a real TimelineBlock on the 'Our Impact' page."

    def add_arguments(self, parser):
        parser.add_argument("--page-id", type=int, help="Page ID to update. Overrides --slug.")
        parser.add_argument(
            "--slug",
            default="our-impact",
            help="Slug of the page to update if --page-id is not given (default: our-impact).",
        )
        parser.add_argument(
            "--source-file",
            help="Parse a manually-saved copy of the page from this local file instead of "
            "fetching it live -- a fallback if the live fetch is ever blocked.",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Actually replace the page's body. Without this flag, the page found (or not "
            "found) is reported and nothing is written -- same skip-unless-update default as "
            "import_350_press_releases.py.",
        )
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Publish the new revision immediately. Without this flag, a draft revision is "
            "saved and the live page is left unchanged until someone reviews and publishes it.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be imported without downloading images or writing to the DB.",
        )

    def handle(self, *args, **options):
        from wagtail.models import Page

        dry_run = options["dry_run"]
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT

        if options["source_file"]:
            with open(options["source_file"]) as f:
                html = f.read()
        else:
            self.stdout.write(f"Fetching {SOURCE_URL} ...")
            html = fetch_our_impact_html(session)

        years = parse_years(html, session, self.stdout, dry_run=dry_run)
        if not years:
            raise CommandError("No year sections found -- the source page's structure may have changed.")

        self.stdout.write(f"Parsed {len(years)} years: {', '.join(y['year'] for y in years)}")
        for y in years:
            block_types = [b["type"] for b in y["content"]]
            self.stdout.write(f"  {y['year']}: {block_types}")

        if options["page_id"]:
            page = Page.objects.filter(pk=options["page_id"]).first()
        else:
            page = Page.objects.filter(slug=options["slug"]).first()
        if page is None:
            raise CommandError(f"No page found (page_id={options['page_id']!r}, slug={options['slug']!r}).")
        page = page.specific

        if not hasattr(page, "body"):
            raise CommandError(f"{page!r} (type {type(page).__name__}) has no 'body' StreamField.")

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"Dry run complete. Would update {page!r}. Nothing written."))
            return

        if not options["update"]:
            self.stdout.write(
                f"Found {page!r} (type {type(page).__name__}). Pass --update to replace its body "
                "with the imported timeline."
            )
            return

        page.body = [_stream_block("timeline", {"years": years})]

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

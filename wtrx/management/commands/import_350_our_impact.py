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
        -> AccordionItemBlock (title from .expando-link; content is
        AccordionItemContentBlock -- a "text" entry from .victory-text
        cleaned to richtext, then an "image" and/or "video" entry for the
        item's own media, in that order, each only present when the item
        actually has one — see wtrx/blocks/__init__.py and AGENTS.md
        pitfall #51).

Video URL handling: a victory item's or year's video is imported as a real
"video" StreamField block either way, using VideoBlock's two mutually
exclusive forms. When Wagtail's own OEmbedFinder recognises the provider
(checked locally via `.accept()`, no network call) -- YouTube and Vimeo do
-- it's a plain `embed_url`. Every video URL on the live page that fails
this check is a 350org.widen.net CDN link whose path looks like a direct
`.mp4` file but isn't one -- it's an HTML page bootstrapping Widen's own
video.js player; the real file lives at a different, signed CloudFront URL
embedded in that page's own JS (see download_video()'s and
_resolve_widen_video_download_url()'s docstrings for exactly how this is
detected and resolved). That real file is downloaded and self-hosted as a
wagtailmedia Media (type="video") via `media_file`, the same
download-once-and-own-it treatment already given to every image on this
page (download_image()) -- more durable than embedding the third-party
player page directly (its own `?u=...` token, and the resolved file's own
signature, are both presumably expiring), and it reuses VideoBlock's
existing, already-styled media_file rendering (poster, responsive wrapper)
in both accordion_block.html and video_block.html, rather than needing any
raw-HTML fallback. Resulting file sizes vary widely by asset (confirmed
24MB-396MB across the 8 real videos on this page as of this writing) -- see
AGENTS.md pitfall #51 if that ever needs revisiting. A video URL matching
neither oEmbed nor a direct-file extension, or whose resolved Widen source
still isn't a real video file, is still skipped with a warning.

Known, deliberately accepted gaps (all logged as warnings, never abort the
run — same per-item failure tolerance as download_image()/rewrite_image_urls()):
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

import json
import os
import re
import uuid
from urllib.parse import urlparse

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

# Matches a direct video-file URL (optionally followed by a "?..." query
# string) -- every video URL on the live page that OEmbedFinder doesn't
# recognise is one of these (350.org's own Widen CDN links), not a
# genuinely unsupported third-party provider.
_DIRECT_VIDEO_FILE_RE = re.compile(r"\.(?:mp4|webm|mov|ogg)(?:\?.*)?$", re.IGNORECASE)


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


_WIDEN_BOOTSTRAP_RE = re.compile(r"window\.bootstrapData\s*=\s*(\{.*?\});\s*</script>", re.DOTALL)
_WIDEN_RESOLUTION_PREFERENCE = ("720p", "480p", "1080p", "360p")


def _resolve_widen_video_download_url(html_text):
    """
    Widen's own hosted "view/video/<id>/<filename>.mp4?u=..." URL (the one
    350.org's page embeds in an <iframe src>, and the only case observed on
    the live page) is not a video file at all, despite the .mp4-looking
    filename in its path -- it's an HTML page bootstrapping a video.js
    player, confirmed by fetching one directly: `Content-Type: text/html`,
    ~5KB. The actual playable file lives at a *different*, signed
    CloudFront URL embedded in that page's own `window.bootstrapData` JSON
    (`previews.files[].source`) -- what the player itself fetches to play
    the video, confirmed by fetching one of those directly:
    `Content-Type: video/mp4`, tens of MB. This extracts that JSON and
    picks one resolution's source URL to download instead.

    Prefers a mid-range resolution (720p, falling back down the
    _WIDEN_RESOLUTION_PREFERENCE list, then whatever's first) over the
    highest available -- these are supplementary broll clips inside an
    accordion item, not the main content, so a smaller self-hosted file is
    a better trade than maximum quality.
    """
    match = _WIDEN_BOOTSTRAP_RE.search(html_text)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
        files = data["previews"]["files"]
    except (ValueError, KeyError, TypeError):
        return None
    by_label = {f.get("label"): f.get("source") for f in files if isinstance(f, dict)}
    for label in _WIDEN_RESOLUTION_PREFERENCE:
        if by_label.get(label):
            return by_label[label]
    return files[0].get("source") if files and isinstance(files[0], dict) else None


def download_video(session, url, stdout, dry_run=False):
    """
    Download a video file from ``url`` and create a wagtailmedia Media
    (type="video"), or return an existing one whose title already matches
    the source filename (dedup across runs, same convention as
    _wp_content_utils.download_image()).

    ``url`` may itself not be a direct file (see
    _resolve_widen_video_download_url()'s docstring) -- if the response's
    Content-Type isn't video/*, this treats the response body as an HTML
    player page and looks for the real file inside it before giving up.

    Unlike CustomImage, wagtailmedia's Media does no file-content processing
    at all on save() -- no Willow/ffmpeg probing; duration defaults to 0 and
    thumbnail/width/height are all optional -- so there's no format-detection
    failure mode to guard against here the way _safe_download_image() does,
    only the network-level one this already handles the same way
    download_image() does.
    """
    if not url:
        return None

    from wagtailmedia.models import Media

    filename = os.path.basename(urlparse(url).path) or "imported-video"
    existing = Media.objects.filter(title=filename, type="video").first()
    if existing:
        return existing

    if dry_run:
        stdout.write(f"    [dry-run] would download video: {url}")
        return None

    from django.core.files.uploadedfile import SimpleUploadedFile

    try:
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        stdout.write(f"    WARNING: failed to download video {url} — {exc}")
        return None

    if not resp.headers.get("Content-Type", "").startswith("video/"):
        download_url = _resolve_widen_video_download_url(resp.text)
        if download_url is None:
            stdout.write(
                f"    WARNING: {url} did not return a video file and no downloadable "
                "source could be found on its page, skipping video"
            )
            return None
        try:
            resp = session.get(download_url, timeout=120)
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            stdout.write(f"    WARNING: failed to download video {download_url} — {exc}")
            return None
        if not resp.headers.get("Content-Type", "").startswith("video/"):
            stdout.write(f"    WARNING: resolved video source {download_url} is not a video file, skipping")
            return None

    uploaded = SimpleUploadedFile(filename, resp.content)
    media = Media(title=filename, file=uploaded, type="video")
    media.save()
    stdout.write(f"    downloaded video: {filename}")
    return media


def _safe_download_video(session, url, stdout, dry_run):
    """
    Wrap download_video() with a broad except, mirroring
    _safe_download_image() -- Media.save() does no file-content processing,
    so there's no Willow-style parse failure to guard against, but the same
    safety net still means one bad video (a write error, a surprising
    response) can't abort an 80+ item import.
    """
    try:
        return download_video(session, url, stdout, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, see docstring
        stdout.write(f"    WARNING: failed to process video {url} — {exc!r}")
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


def _video_value(container, session, stdout, dry_run, context):
    """
    Return a VideoBlock-shaped {embed_url, media_file, caption} dict for the
    first <iframe src> inside ``container``, or None if there's no usable
    video.

    - embed_url set (media_file None) when Wagtail's own OEmbedFinder
      recognises the provider (a pure local regex match against the
      provider list -- no network call) -- YouTube and Vimeo do.
    - media_file set to a downloaded wagtailmedia Media's pk (embed_url "")
      when the provider isn't recognised but the src is a direct video-file
      link. Every such case on the live page is a 350.org's own
      350org.widen.net CDN link, whose URLs carry a signed, presumably-
      expiring `?u=...` token -- downloading and self-hosting the file is
      more durable than embedding that link directly, and it reuses
      VideoBlock's existing, already-styled media_file rendering (poster,
      responsive wrapper) with no raw-HTML fallback needed. See
      download_video().
    - None (with a printed warning) for anything else -- a URL Wagtail
      can't resolve and isn't a direct file link either would render
      nothing via {% embed %} anyway (video_block.html/accordion_block.html
      both branch on embed_url/media_file being set), so there's nothing
      useful to do with it. No such case is known on the live page today;
      this is a safety net in case the source page ever adds one. Also
      returned (with a warning already printed by _safe_download_video())
      if a direct-file download fails.
    """
    from wagtail.embeds.finders.oembed import OEmbedFinder

    iframe = container.find("iframe")
    if iframe is None or not iframe.get("src"):
        return None
    src = _normalize_video_url(iframe["src"])
    if OEmbedFinder().accept(src):
        return {"embed_url": src, "media_file": None, "caption": ""}
    if _DIRECT_VIDEO_FILE_RE.search(src):
        media = _safe_download_video(session, src, stdout, dry_run=dry_run)
        if media is not None:
            return {"embed_url": "", "media_file": media.pk, "caption": ""}
        return None
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
    text = _clean_fragment(text_container)

    content = []
    if text:
        content.append(_stream_block("text", text))

    img_tag = inner.find("img")
    if img_tag is not None and img_tag.get("src"):
        image = _safe_download_image(session, img_tag["src"], stdout, dry_run=dry_run)
        if image is not None:
            content.append(
                _stream_block(
                    "image", {"image": image.pk, "alt_text": img_tag.get("alt", ""), "caption": ""}
                )
            )

    video_container = inner.find("div", class_="video-container")
    if video_container is not None:
        video_value = _video_value(
            video_container, session, stdout, dry_run, context=f"victory item {title!r}"
        )
        if video_value is not None:
            content.append(_stream_block("video", video_value))

    return {
        "title": title,
        "content": content,
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
            video_value = _video_value(node, session, stdout, dry_run, context="year video")
            if video_value is not None:
                blocks.append(_stream_block("video", video_value))
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

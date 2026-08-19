"""
import_350_blog management command.

Fetches posts from 350.org's WordPress REST API (https://350.org/wp-json/wp/v2/posts)
and imports them as wtrx.BlogPage instances under the site's BlogIndexPage.

Usage:
    python manage.py import_350_blog                      # last 20 posts (default)
    python manage.py import_350_blog --limit 100
    python manage.py import_350_blog --since 2026-01-01
    python manage.py import_350_blog --dry-run             # preview only, no DB writes
    python manage.py import_350_blog --update              # overwrite already-imported posts

Field mapping:
    WP title/slug/date_gmt   -> BlogPage title/slug/published_at
    WP content.rendered      -> BlogPage.body (StreamField: text + image blocks)
    WP featured media        -> BlogPage.hero_image
    WP categories (subset)   -> BlogPage.categories (see CATEGORY_SLUG_MAP)
    WP author name           -> BlogPage.author_name (BlogPage.author, the FK to a
                                 site login user, is left blank — imported posts
                                 aren't written by staff accounts)

CATEGORY_SLUG_MAP is a deliberately narrow allowlist: only WordPress category
slugs listed here are mapped onto wtrx.BlogCategory. Anything else is ignored,
so imported posts may have zero categories rather than a guessed one.
"""

import html
import os
import uuid
from datetime import timezone as dt_timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from django.core.management.base import BaseCommand
from django.utils import timezone as dj_timezone
from django.utils.dateparse import parse_datetime

WP_API_URL = "https://350.org/wp-json/wp/v2/posts"
USER_AGENT = "350-wagtail-blog-import/1.0 (+https://github.com/)"

# WordPress category slug -> wtrx.BlogCategory name. Only these are imported;
# every other WP category is ignored.
CATEGORY_SLUG_MAP = {
    "kiitg": "stop fossil fuels",
    "finance": "fossil finance",
    "solutions": "renewable solutions",
}

# Block-level tags kept as-is (mapped to themselves or normalized), matching
# wtrx.constants.RICHTEXT_FEATURES_FULL: h2/h3/h4, lists, blockquote.
_BLOCK_TAG_MAP = {
    "h1": "h2",
    "h2": "h2",
    "h3": "h3",
    "h4": "h4",
    "h5": "h4",
    "h6": "h4",
    "p": "p",
    "ul": "ul",
    "ol": "ol",
    "li": "li",
    "blockquote": "blockquote",
}

# Inline tags kept as-is, matching RICHTEXT_FEATURES_FULL: bold, italic, link.
_INLINE_TAG_MAP = {
    "strong": "strong",
    "b": "strong",
    "em": "em",
    "i": "em",
    "a": "a",
    "br": "br",
}

# Tags dropped entirely, along with their contents.
_DROP_ENTIRELY = {"script", "style", "noscript", "iframe", "form", "svg", "button", "input"}

_TAG_FACTORY = BeautifulSoup("", "html.parser")


def _build_clean(node):
    """
    Recursively rebuild a bs4 node's subtree using only tags allowed by
    RICHTEXT_FEATURES_FULL, unwrapping (keeping children/text of) anything
    else and dropping _DROP_ENTIRELY tags along with their contents.

    Returns a list of cleaned bs4 nodes (Tag/NavigableString) suitable for
    appending into a parent tag or serializing directly with str().
    """
    if isinstance(node, Comment):
        return []
    if isinstance(node, NavigableString):
        return [NavigableString(str(node))]
    if not isinstance(node, Tag):
        return []

    name = node.name.lower()
    if name in _DROP_ENTIRELY:
        return []

    mapped = _BLOCK_TAG_MAP.get(name) or _INLINE_TAG_MAP.get(name)
    if not mapped:
        # Unknown/disallowed wrapper (span, div, font, u, sup, ...) — unwrap.
        result = []
        for child in node.children:
            result.extend(_build_clean(child))
        return result

    if mapped == "a":
        href = node.get("href")
        if not href:
            result = []
            for child in node.children:
                result.extend(_build_clean(child))
            return result
        new_tag = _TAG_FACTORY.new_tag("a", href=href)
    else:
        new_tag = _TAG_FACTORY.new_tag(mapped)

    for child in node.children:
        for cleaned_child in _build_clean(child):
            new_tag.append(cleaned_child)
    return [new_tag]


def _download_image(session, url, stdout, dry_run=False):
    """
    Download an image from ``url`` and create a CustomImage, or return an
    existing one whose title already matches the source filename (dedup
    across runs, since CustomImage has no dedicated external-URL field).
    """
    if not url:
        return None

    # Deferred import to avoid import-time DB access.
    from wtrx.images import CustomImage

    filename = os.path.basename(urlparse(url).path) or "imported-image"
    existing = CustomImage.objects.filter(title=filename).first()
    if existing:
        return existing

    if dry_run:
        stdout.write(f"    [dry-run] would download image: {url}")
        return None

    from django.core.files.uploadedfile import SimpleUploadedFile

    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    uploaded = SimpleUploadedFile(filename, resp.content)
    image = CustomImage(title=filename, file=uploaded)
    image.save()
    stdout.write(f"    downloaded image: {filename}")
    return image


def _make_image_block(img_tag, caption, session, stdout, dry_run=False):
    if img_tag is None:
        return None
    src = img_tag.get("src")
    if not src:
        return None
    image = _download_image(session, src, stdout, dry_run=dry_run)
    if image is None:
        return None
    return {
        "type": "image",
        "value": {
            "image": image.pk,
            "alt_text": img_tag.get("alt", ""),
            "caption": caption,
        },
    }


def _process_nodes(nodes, blocks, pending, session, stdout, dry_run=False):
    """
    Walk a list of top-level bs4 nodes, appending finished blocks to
    ``blocks`` and accumulating consecutive text-eligible HTML fragments in
    ``pending`` (flushed into a single "text" block on any break).
    """

    def flush():
        if not pending:
            return
        combined = "".join(pending).strip()
        pending.clear()
        if combined:
            blocks.append({"type": "text", "value": combined})

    for node in nodes:
        if isinstance(node, Comment):
            continue
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                p = _TAG_FACTORY.new_tag("p")
                p.append(NavigableString(text))
                pending.append(str(p))
            continue
        if not isinstance(node, Tag):
            continue

        name = node.name.lower()
        if name in _DROP_ENTIRELY:
            continue

        # WP's captioned-image wrapper: <div class="wp-caption">...<img>...
        # <p class="wp-caption-text">caption</p></div>, or a <figure>/<figcaption>.
        if name in ("div", "figure") and node.find("img"):
            img_tag = node.find("img")
            caption_tag = node.find(class_="wp-caption-text") or node.find("figcaption")
            caption = caption_tag.get_text(strip=True) if caption_tag else ""
            flush()
            block = _make_image_block(img_tag, caption, session, stdout, dry_run=dry_run)
            if block:
                blocks.append(block)
            continue

        if name == "img":
            flush()
            block = _make_image_block(node, "", session, stdout, dry_run=dry_run)
            if block:
                blocks.append(block)
            continue

        if name in _BLOCK_TAG_MAP:
            imgs = node.find_all("img")
            if imgs and not node.get_text(strip=True):
                # A block whose only content is one or more bare images
                # (e.g. <p><img></p>), no surrounding text.
                flush()
                for img_tag in imgs:
                    block = _make_image_block(img_tag, "", session, stdout, dry_run=dry_run)
                    if block:
                        blocks.append(block)
                continue
            for cleaned in _build_clean(node):
                text = cleaned.get_text(strip=True) if isinstance(cleaned, Tag) else str(cleaned).strip()
                if text:
                    pending.append(str(cleaned))
            continue

        # Unrecognized wrapper tag (div/section with no image, etc.) — flatten
        # by treating its children as if they were top-level nodes.
        _process_nodes(list(node.children), blocks, pending, session, stdout, dry_run=dry_run)

    flush()


def convert_body(content_html, session, stdout, dry_run=False):
    fragment = BeautifulSoup(content_html or "", "html.parser")
    blocks = []
    pending = []
    _process_nodes(list(fragment.children), blocks, pending, session, stdout, dry_run=dry_run)
    for block in blocks:
        block["id"] = str(uuid.uuid4())
    return blocks


def _parse_published_at(post):
    dt = parse_datetime(post.get("date_gmt") or post.get("date") or "")
    if dt is None:
        return dj_timezone.now()
    if dj_timezone.is_naive(dt):
        dt = dj_timezone.make_aware(dt, dt_timezone.utc)
    return dt


def _category_names(post):
    embedded_terms = post.get("_embedded", {}).get("wp:term", [])
    slugs = set()
    for group in embedded_terms:
        for term in group:
            if term.get("taxonomy") == "category":
                slugs.add(term.get("slug"))
    names = {CATEGORY_SLUG_MAP[slug] for slug in slugs if slug in CATEGORY_SLUG_MAP}
    return names


def _author_name(post):
    embedded_authors = post.get("_embedded", {}).get("author") or []
    if not embedded_authors:
        return ""
    name = embedded_authors[0].get("name") or ""
    return html.unescape(name)


def _featured_image_url(post):
    embedded_media = post.get("_embedded", {}).get("wp:featuredmedia") or []
    if not embedded_media:
        return None
    media = embedded_media[0]
    if media.get("code"):  # e.g. {"code": "rest_forbidden", ...} when media 404s
        return None
    return media.get("source_url")


def fetch_posts(session, limit=None, since=None):
    params = {"orderby": "date", "order": "desc", "_embed": 1}
    if since:
        params["after"] = f"{since}T00:00:00"
    params["per_page"] = min(limit, 100) if limit else 100

    page = 1
    fetched = 0
    while True:
        params["page"] = page
        resp = session.get(WP_API_URL, params=params, timeout=30)
        resp.raise_for_status()
        posts = resp.json()
        if not posts:
            return
        for post in posts:
            yield post
            fetched += 1
            if limit and fetched >= limit:
                return
        total_pages = int(resp.headers.get("X-WP-TotalPages", page))
        if page >= total_pages:
            return
        page += 1


class Command(BaseCommand):
    help = "Import blog posts from 350.org's WordPress REST API as wtrx.BlogPage instances."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Maximum number of posts to import, most recent first (default: 20). "
            "Use 0 for no limit.",
        )
        parser.add_argument(
            "--since",
            help="Only import posts published on/after this date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be imported without writing to the database.",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Overwrite BlogPages that were already imported (matched by slug), "
            "instead of skipping them.",
        )

    def handle(self, *args, **options):
        # Deferred imports to avoid import-time DB access (architecture rule #4).
        from wtrx.models import BlogCategory, BlogIndexPage, BlogPage

        limit = options["limit"] or None
        since = options["since"]
        dry_run = options["dry_run"]
        update = options["update"]

        blog_index = BlogIndexPage.objects.first()
        if blog_index is None:
            self.stderr.write(self.style.ERROR("No BlogIndexPage found. Create one first."))
            return

        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT

        category_cache = {}

        def get_categories(names):
            result = []
            for name in names:
                if name not in category_cache:
                    category_cache[name], _ = BlogCategory.objects.get_or_create(name=name)
                result.append(category_cache[name])
            return result

        created, updated, skipped = 0, 0, 0

        for post in fetch_posts(session, limit=limit, since=since):
            title = html.unescape(post["title"]["rendered"])
            slug = post["slug"]

            existing = BlogPage.objects.child_of(blog_index).filter(slug=slug).first()
            if existing and not update:
                self.stdout.write(f"  skip (already imported): {slug}")
                skipped += 1
                continue

            self.stdout.write(f"{'updating' if existing else 'importing'}: {title}")

            published_at = _parse_published_at(post)
            categories = get_categories(_category_names(post))
            body = convert_body(post["content"]["rendered"], session, self.stdout, dry_run=dry_run)
            author_name = _author_name(post)

            hero_image = None
            featured_url = _featured_image_url(post)
            if featured_url:
                hero_image = _download_image(session, featured_url, self.stdout, dry_run=dry_run)

            if dry_run:
                self.stdout.write(
                    f"    [dry-run] title={title!r} slug={slug!r} published_at={published_at} "
                    f"author_name={author_name!r} categories={[c.name for c in categories]} "
                    f"blocks={len(body)}"
                )
                continue

            if existing:
                existing.title = title
                existing.published_at = published_at
                existing.hero_image = hero_image
                existing.body = body
                existing.author_name = author_name
                existing.save()
                existing.categories.set(categories)
                updated += 1
            else:
                page = BlogPage(
                    title=title,
                    slug=slug,
                    author_name=author_name,
                    published_at=published_at,
                    hero_image=hero_image,
                    body=body,
                )
                blog_index.add_child(instance=page)
                page.categories.set(categories)
                created += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run complete — no changes written."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Done. Created {created}, updated {updated}, skipped {skipped}.")
            )

"""
import_350_press_releases management command.

350.org's press releases are a custom WordPress post type that is NOT
exposed via the WP REST API (unlike regular posts — see import_350_blog.py).
Confirmed: /wp-json/wp/v2/types lists no press-release type, and
/wp-json/wp/v2/press-release(s) 404s. Instead this scrapes the live pages,
discovering their URLs from Yoast's dedicated XML sitemap
(https://350.org/press-release-sitemap*.xml), which is complete and already
sorted oldest-to-newest.

Usage:
    python manage.py import_350_press_releases                # last 20 (default)
    python manage.py import_350_press_releases --limit 100
    python manage.py import_350_press_releases --since 2026-01-01
    python manage.py import_350_press_releases --dry-run        # preview only
    python manage.py import_350_press_releases --update         # overwrite already-imported

Field mapping:
    Page <h2> in #press-release-header  -> Post.title
    URL slug                            -> Post.slug
    "#post-time" text (e.g. "August 19, 2026") -> Post.published_at
    <article class="clearfix"> content  -> Post.body (StreamField)

Post's author/categories/hero_image are all optional (see wtrx.models) and
deliberately left unset here — a press release has no byline or category,
and with hero_headline/hero_image blank the hero banner just renders the
title and date. A leading image inside the article content simply becomes
the first "image" block in the body, same as any other inline image.
"""

import html
import re
from datetime import datetime
from datetime import timezone as dt_timezone

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.utils import timezone as dj_timezone

from wtrx.management.commands._wp_content_utils import convert_body

SITEMAP_INDEX_URL = "https://350.org/sitemap_index.xml"
USER_AGENT = "350-wagtail-press-release-import/1.0 (+https://github.com/)"

_LOC_RE = re.compile(r"<loc>(.*?)</loc>")


def _sitemap_shard_urls(session):
    resp = session.get(SITEMAP_INDEX_URL, timeout=30)
    resp.raise_for_status()
    return [
        loc for loc in _LOC_RE.findall(resp.text) if "press-release-sitemap" in loc
    ]


def fetch_press_release_urls(session):
    """
    Return every press release URL, most recently published first.

    The sitemap shards are each internally oldest-to-newest, and later
    shards contain newer posts than earlier ones (verified against the
    live /media page), so concatenating shards in document order and
    reversing the combined list gives newest-first.
    """
    urls = []
    for shard_url in _sitemap_shard_urls(session):
        resp = session.get(shard_url, timeout=30)
        resp.raise_for_status()
        for url in _LOC_RE.findall(resp.text):
            if url.rstrip("/").endswith("/press-release"):
                continue  # the archive index itself, not a single post
            urls.append(url)
    urls.reverse()
    return urls


def _slug_from_url(url):
    return url.rstrip("/").rsplit("/", 1)[-1]


def fetch_press_release(session, url):
    """
    Fetch and parse a single press release page.

    Returns (title, published_at, body_blocks), or None if the page is
    missing the expected structure (title or article content).
    """
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    header = soup.find(id="press-release-header")
    title_tag = header.find("h2") if header else None
    if title_tag is None:
        return None
    title = html.unescape(title_tag.get_text(strip=True))

    published_at = dj_timezone.now()
    date_span = soup.find(id="post-time")
    if date_span:
        try:
            dt = datetime.strptime(date_span.get_text(strip=True), "%B %d, %Y")
            published_at = dj_timezone.make_aware(dt, dt_timezone.utc)
        except ValueError:
            pass

    article = soup.find("article", class_="clearfix")
    if article is None:
        return None

    return title, published_at, str(article)


class Command(BaseCommand):
    help = "Import press releases from 350.org/media as wtrx.Post instances."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Maximum number of press releases to import, most recent first "
            "(default: 20). Use 0 for no limit.",
        )
        parser.add_argument(
            "--since",
            help="Only import press releases published on/after this date (YYYY-MM-DD). "
            "Stops as soon as an older one is reached (list is newest-first).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be imported without writing to the database.",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Overwrite Posts that were already imported (matched by "
            "slug), instead of skipping them.",
        )

    def handle(self, *args, **options):
        # Deferred imports to avoid import-time DB access (architecture rule #4).
        from wtrx.models import Blogs, Post

        limit = options["limit"] or None
        since = options["since"]
        since_date = datetime.strptime(since, "%Y-%m-%d").date() if since else None
        dry_run = options["dry_run"]
        update = options["update"]

        blogs_index = Blogs.objects.first()
        if blogs_index is None:
            self.stderr.write(self.style.ERROR("No Blogs page found. Create one first."))
            return

        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT

        self.stdout.write("Fetching press release list from sitemap…")
        urls = fetch_press_release_urls(session)
        self.stdout.write(f"Found {len(urls)} press releases total.")

        created, updated, skipped = 0, 0, 0
        processed = 0

        for url in urls:
            if limit and processed >= limit:
                break

            slug = _slug_from_url(url)
            existing = Post.objects.child_of(blogs_index).filter(slug=slug).first()
            if existing and not update:
                self.stdout.write(f"  skip (already imported): {slug}")
                skipped += 1
                processed += 1
                continue

            parsed = fetch_press_release(session, url)
            if parsed is None:
                self.stdout.write(self.style.WARNING(f"  skip (unrecognized page structure): {url}"))
                continue
            title, published_at, content_html = parsed

            if since_date and published_at.date() < since_date:
                self.stdout.write(f"  reached --since cutoff at: {slug}")
                break

            processed += 1
            self.stdout.write(f"{'updating' if existing else 'importing'}: {title}")

            body = convert_body(content_html, session, self.stdout, dry_run=dry_run)

            if dry_run:
                self.stdout.write(
                    f"    [dry-run] title={title!r} slug={slug!r} published_at={published_at} "
                    f"blocks={len(body)}"
                )
                continue

            if existing:
                existing.title = title
                existing.published_at = published_at
                existing.body = body
                existing.save()
                updated += 1
            else:
                page = Post(
                    title=title,
                    slug=slug,
                    published_at=published_at,
                    body=body,
                )
                blogs_index.add_child(instance=page)
                created += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run complete — no changes written."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Done. Created {created}, updated {updated}, skipped {skipped}.")
            )

"""
import_350_blog management command.

Fetches posts from 350.org's WordPress REST API (https://350.org/wp-json/wp/v2/posts)
and imports them as wtrx.Post instances under the site's Blogs page.

Usage:
    python manage.py import_350_blog                      # last 20 posts (default)
    python manage.py import_350_blog --limit 100
    python manage.py import_350_blog --since 2026-01-01
    python manage.py import_350_blog --dry-run             # preview only, no DB writes
    python manage.py import_350_blog --update              # overwrite already-imported posts

Field mapping:
    WP title/slug/date_gmt   -> Post title/slug/published_at
                                (also first_published_at, which Wagtail
                                only sets on an admin publish)
    WP content.rendered      -> Post.body (StreamField: text + image blocks)
    WP featured media        -> Post.hero_image
    WP categories (subset)   -> Post.categories (see CATEGORY_SLUG_MAP,
                                 falling back to title-keyword matching --
                                 see TITLE_CATEGORY_KEYWORDS)
    WP "Hide from main blogroll" category -> Post.hide_from_blogroll
    WP author name           -> Post.author_name (Post.author, the FK to a
                                 site login user, is left blank — imported posts
                                 aren't written by staff accounts). The live
                                 page's <span class="post-author"> byline is
                                 preferred over the REST API's embedded author,
                                 since guest-contributor posts show a byline
                                 there that differs from the API's WP user.
    Yoast SEO title/description (yoast_head_json) -> Post.seo_title /
                                 Post.search_description. The " - <Site
                                 Name>" suffix Yoast's title template adds is
                                 stripped. Left blank if Yoast has none set.

CATEGORY_SLUG_MAP is a deliberately narrow allowlist mapping specific
WordPress category slugs directly onto wtrx.BlogCategory names -- these are
exact/known equivalents (e.g. WP's "kiitg" category *is* our "Fossil Fuels"
category), not a guess. A post carrying none of these WP categories falls
back to TITLE_CATEGORY_KEYWORDS: a simple case-insensitive substring match
of the post title against each of the 5 target categories' keyword list. A
post can end up in more than one category, from either source, and a title
that matches nothing keeps zero categories rather than a forced guess.
"""

import html
from datetime import timezone as dt_timezone

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.utils import timezone as dj_timezone
from django.utils.dateparse import parse_datetime

from wtrx.management.commands._wp_content_utils import (
    convert_body,
    download_image,
    resolve_blogs_target,
    yoast_seo_fields_from_api_post,
)

WP_API_URL = "https://350.org/wp-json/wp/v2/posts"
USER_AGENT = "350-wagtail-blog-import/1.0 (+https://github.com/)"

# WordPress category slug -> wtrx.BlogCategory name. Only known direct
# equivalents belong here -- "justice" is WP's own literal "Climate Justice"
# category, not a guess. "impacts" (WP's "Climate Impacts") is deliberately
# excluded: it's broader than Extreme Weather (sea-level rise, biodiversity,
# etc. all live under it too), so posts carrying it fall through to the
# title-keyword match instead of being assumed to be about extreme weather.
CATEGORY_SLUG_MAP = {
    "kiitg": "Fossil Fuels",
    "finance": "Climate Finance",
    "solutions": "Renewable Energy",
    "justice": "Climate Justice",
}

# WP category slug flagging a post to be hidden from the main blog listing
# (WP's own "Hide from main blogroll" category) -> Post.hide_from_blogroll.
HIDE_FROM_BLOGROLL_SLUG = "hide-from-main-blogroll"

# Fallback for posts with none of CATEGORY_SLUG_MAP's WP categories: a
# case-insensitive substring match of the post title against each target
# category's keyword list. Order doesn't matter -- every matching category
# is applied, same as a post carrying multiple WP categories would be.
TITLE_CATEGORY_KEYWORDS = {
    "Fossil Fuels": [
        "fossil fuel", "oil ", "coal", "pipeline", "drilling", "fracking",
        "petroleum", "lng", "keep it in the ground", "gas company", "gas companies",
        "gas field", "gas project", "refinery",
    ],
    "Renewable Energy": [
        "renewable", "solar", "wind power", "wind energy", "wind farm",
        "clean energy", "green energy", "electric vehicle", "battery storage",
    ],
    "Climate Finance": [
        "divest", "divestment", "bank", "insurer", "insurance", "world bank",
        "imf", "climate finance", "fossil fuel finance", "loan", "investor",
        "investment", "funding",
    ],
    "Climate Justice": [
        "justice", "equity", "indigenous", "frontline communities",
        "human rights", "reparations", "just transition", "colonial",
    ],
    "Extreme Weather": [
        "flood", "wildfire", "hurricane", "typhoon", "cyclone", "drought",
        "heatwave", "heat wave", "extreme heat", "extreme weather", "climate disaster",
        "monsoon", "landslide", "tornado", "storm",
    ],
}


def _parse_published_at(post):
    dt = parse_datetime(post.get("date_gmt") or post.get("date") or "")
    if dt is None:
        return dj_timezone.now()
    if dj_timezone.is_naive(dt):
        dt = dj_timezone.make_aware(dt, dt_timezone.utc)
    return dt


def _wp_category_slugs(post):
    embedded_terms = post.get("_embedded", {}).get("wp:term", [])
    slugs = set()
    for group in embedded_terms:
        for term in group:
            if term.get("taxonomy") == "category":
                slugs.add(term.get("slug"))
    return slugs


def _categorize_by_title(title):
    lowered = title.lower()
    return {
        name
        for name, keywords in TITLE_CATEGORY_KEYWORDS.items()
        if any(keyword in lowered for keyword in keywords)
    }


def _category_names(post, title):
    slugs = _wp_category_slugs(post)
    names = {CATEGORY_SLUG_MAP[slug] for slug in slugs if slug in CATEGORY_SLUG_MAP}
    if names:
        return names
    return _categorize_by_title(title)


def _is_hidden_from_blogroll(post):
    return HIDE_FROM_BLOGROLL_SLUG in _wp_category_slugs(post)


def _author_name(post, session):
    """
    Resolve the byline to display for a post.

    The REST API's embedded author is whichever WP user account is logged
    in as the post's author — often a shared staff/editor login — while a
    guest contributor's byline (rendered by a plugin as
    ``<span class="post-author">`` on the live page, e.g. "Camilo Sánchez"
    on a post whose WP author is a comms account) exists only in the
    rendered page, not the API. Scrape the live page for the true displayed
    byline so guest bylines import correctly, falling back to the API's
    embedded name if the page fetch fails or has no visible byline (this
    also covers ordinary, non-guest posts, where both sources agree).
    """
    embedded_authors = post.get("_embedded", {}).get("author") or []
    fallback = html.unescape(embedded_authors[0].get("name") or "") if embedded_authors else ""

    link = post.get("link")
    if not link:
        return fallback
    try:
        resp = session.get(link, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.RequestException:
        return fallback

    soup = BeautifulSoup(resp.text, "html.parser")
    span = soup.find("span", class_="post-author")
    if span:
        text = html.unescape(span.get_text(strip=True))
        if text:
            return text
    return fallback


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
    help = "Import blog posts from 350.org's WordPress REST API as wtrx.Post instances."

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
            help="Overwrite Posts that were already imported (matched by slug), "
            "instead of skipping them.",
        )
        parser.add_argument(
            "--target",
            help="Slug of the Blogs page to import under. Required if more than one "
            "Blogs page exists; optional (and inferred) if there's only one.",
        )

    def handle(self, *args, **options):
        # Deferred imports to avoid import-time DB access (architecture rule #4).
        from wtrx.models import BlogCategory, Post

        limit = options["limit"] or None
        since = options["since"]
        dry_run = options["dry_run"]
        update = options["update"]

        blogs_index = resolve_blogs_target(self.stderr, self.style, options["target"])
        if blogs_index is None:
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

            existing = Post.objects.child_of(blogs_index).filter(slug=slug).first()
            if existing and not update:
                self.stdout.write(f"  skip (already imported): {slug}")
                skipped += 1
                continue

            self.stdout.write(f"{'updating' if existing else 'importing'}: {title}")

            published_at = _parse_published_at(post)
            categories = get_categories(_category_names(post, title))
            hide_from_blogroll = _is_hidden_from_blogroll(post)
            body = convert_body(post["content"]["rendered"], session, self.stdout, dry_run=dry_run)
            author_name = _author_name(post, session)
            seo_title, search_description = yoast_seo_fields_from_api_post(post)

            hero_image = None
            featured_url = _featured_image_url(post)
            if featured_url:
                hero_image = download_image(session, featured_url, self.stdout, dry_run=dry_run)

            if dry_run:
                self.stdout.write(
                    f"    [dry-run] title={title!r} slug={slug!r} published_at={published_at} "
                    f"author_name={author_name!r} categories={[c.name for c in categories]} "
                    f"hide_from_blogroll={hide_from_blogroll} "
                    f"seo_title={seo_title!r} search_description={search_description!r} "
                    f"blocks={len(body)}"
                )
                continue

            if existing:
                existing.title = title
                existing.published_at = published_at
                # Only fill it in when it is missing: a page published through
                # the admin since the last import has a real value that must not
                # be overwritten by the source's date.
                existing.first_published_at = (
                    existing.first_published_at or published_at
                )
                existing.hero_image = hero_image
                existing.body = body
                existing.author_name = author_name
                existing.hide_from_blogroll = hide_from_blogroll
                existing.seo_title = seo_title
                existing.search_description = search_description
                # categories is a ParentalManyToManyField (django-modelcluster):
                # .set() only caches the change in memory -- it's flushed to the
                # DB by the *next* .save() call (ClusterableModel.commit()), so
                # it must be called before save(), not after.
                existing.categories.set(categories)
                existing.save()
                updated += 1
            else:
                page = Post(
                    title=title,
                    slug=slug,
                    author_name=author_name,
                    seo_title=seo_title,
                    search_description=search_description,
                    published_at=published_at,
                    # Wagtail only sets first_published_at when a page is
                    # published through the admin, so an imported page would
                    # otherwise have none. Anything ordering by it then sorts on
                    # mostly-NULL data -- and PostgreSQL puts NULLs *first* under
                    # DESC, so genuinely recent pages sink below every import.
                    # PageCardsBlock ("3 most recently published") is the visible
                    # casualty. See `manage.py backfill_first_published`, which
                    # repairs content imported before this was set here.
                    first_published_at=published_at,
                    hero_image=hero_image,
                    hide_from_blogroll=hide_from_blogroll,
                    body=body,
                )
                blogs_index.add_child(instance=page)
                # Same ParentalManyToManyField deferred-write behavior as
                # above: add_child() already saved the page once (to assign
                # its tree position), but categories still needs a save()
                # after set() to actually commit to the DB.
                page.categories.set(categories)
                page.save()
                created += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run complete — no changes written."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Done. Created {created}, updated {updated}, skipped {skipped}.")
            )

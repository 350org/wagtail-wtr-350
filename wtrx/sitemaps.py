"""
A sitemap covering every language tree, not just the default one.

Wagtail's own `Sitemap.items()` is
`site.root_page.get_descendants(inclusive=True)`, which is right for a site
whose content all hangs below one root. Here each language is its own tree at
Root level (see `wtrx/i18n.py`), so the country sites are *siblings* of the
English home rather than descendants of it -- and Wagtail's sitemap silently
drops every one of their pages.

The trees are found the same way routing finds them: each language root is a
translation of the site root, which is exactly what gives it a URL
(`Site.get_site_root_paths()` walks `root_page.get_translations()`). Anything
under Root that is *not* such a translation has no URL either, so leaving it
out is correct rather than an omission.

It is also written straight from database values, with no model instances, no
per-page `reverse()` and no template. The production container is capped at
about a third of a CPU, and a sitemap of ~9,000 pages built Wagtail's way cost
3.5 CPU-seconds there -- 13 to 30 seconds of wall time, holding a worker
throughout. Wagtail still builds each language tree's base URL
(`root.get_full_url()`); a page's URL is that plus the rest of its `url_path`,
quoted as `reverse()` quotes it. A test asserts the result matches
`Page.full_url` for every page.

What this gives up: a page type that overrides `get_sitemap_urls()` or
`get_url_parts()` is not consulted (`BasePage.hide_from_search` is applied as
a query instead), and there is no pagination, so the sitemap protocol's limit
of 50,000 URLs per file is not handled.
"""

from urllib.parse import quote
from xml.sax.saxutils import escape

from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.http import RFC3986_SUBDELIMS
from django.views.decorators.cache import cache_control

from wagtail.models import Page, Site, get_page_models

#: How long the CDN may keep the sitemap. The view sets its own Cache-Control,
#: so EdgeCacheMiddleware leaves it alone: an hour stale costs nothing, where a
#: page's 10 minutes meant nearly every crawler fetch found it expired.
SITEMAP_EDGE_CACHE_SECONDS = 60 * 60

#: The characters `django.urls.reverse()` leaves unquoted in a path.
URL_SAFE_CHARACTERS = RFC3986_SUBDELIMS + "/~:@"

XML_HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
XML_TAIL = "</urlset>\n"


def _hidden_page_ids():
    """Primary keys of every page with `hide_from_search` set."""
    from wtrx.models import BasePage

    hidden = set()
    for model in get_page_models():
        if issubclass(model, BasePage):
            hidden.update(model.objects.filter(hide_from_search=True).values_list("pk", flat=True))
    return hidden


def sitemap_entries(request):
    """
    Yield `(url, lastmod)` for every live, public page in every language tree
    of the current site, in tree order.
    """
    site = Site.find_for_request(request) or Site.objects.select_related("root_page").get(is_default_site=True)

    # inclusive=True so each language's own home page is listed too. A root
    # with no URL is a tree nothing routes to.
    trees = []
    subtrees = Q()
    for root in site.root_page.get_translations(inclusive=True):
        base_url = root.get_full_url(request)
        if base_url:
            trees.append((root.path, len(root.url_path), base_url))
            subtrees |= Q(path__startswith=root.path, depth__gte=root.depth)

    if not trees:
        return

    rows = (
        Page.objects.filter(subtrees)
        .live()
        .public()
        .exclude(pk__in=_hidden_page_ids())
        .order_by("path")
        .values_list("path", "url_path", "last_published_at", "latest_revision_created_at")
    )
    for path, url_path, last_published_at, latest_revision_created_at in rows.iterator():
        for root_path, root_url_path_length, base_url in trees:
            if path.startswith(root_path):
                url = base_url + quote(url_path[root_url_path_length:], safe=URL_SAFE_CHARACTERS)
                # Wagtail's own fallback, for pages published before
                # last_published_at existed.
                yield url, last_published_at or latest_revision_created_at
                break


@cache_control(public=True, max_age=0, s_maxage=SITEMAP_EDGE_CACHE_SECONDS)
def sitemap(request):
    """Serve sitemap.xml."""
    parts = [XML_HEAD]
    for url, lastmod in sitemap_entries(request):
        if lastmod:
            parts.append(f"<url><loc>{escape(url)}</loc><lastmod>{timezone.localtime(lastmod):%Y-%m-%d}</lastmod></url>\n")
        else:
            parts.append(f"<url><loc>{escape(url)}</loc></url>\n")
    parts.append(XML_TAIL)
    response = HttpResponse("".join(parts), content_type="application/xml")
    # As Django's own sitemap view sets: the file itself is not a search result.
    response["X-Robots-Tag"] = "noindex, noodp, noarchive"
    return response

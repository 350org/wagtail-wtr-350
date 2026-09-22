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
"""

from django.db.models import Q

from wagtail.contrib.sitemaps import Sitemap as WagtailSitemap
from wagtail.models import Page


class AllLocalesSitemap(WagtailSitemap):
    """Every live, public page in every language tree of the current site."""

    def items(self):
        site = self.get_wagtail_site()

        # inclusive=True so each language's own home page is listed too.
        roots = site.root_page.get_translations(inclusive=True).only("path", "depth")

        subtrees = Q()
        for root in roots:
            subtrees |= Q(path__startswith=root.path, depth__gte=root.depth)

        if not subtrees:
            return Page.objects.none()

        return (
            Page.objects.filter(subtrees)
            .live()
            .public()
            .order_by("path")
            .defer_streamfields()
            .specific()
        )

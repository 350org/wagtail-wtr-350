from django.shortcuts import render

from wagtail.models import Page


def search(request):
    search_query = request.GET.get("query", None)

    if search_query:
        # Search all live pages, then post-filter pages that have opted out.
        # hide_from_search sits on each concrete BasePage subclass table, so a
        # single-query ORM filter is not possible without a raw join. The
        # post-filter approach is the accepted Wagtail pattern.
        raw_results = Page.objects.live().search(search_query)
        search_results = [
            p for p in raw_results if not getattr(p.specific, "hide_from_search", False)
        ]
    else:
        search_results = []

    return render(
        request,
        "wtrx/search/search.html",
        {
            "search_query": search_query,
            "search_results": search_results,
        },
    )

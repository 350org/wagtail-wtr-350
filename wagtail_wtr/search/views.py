from django.shortcuts import render

from wagtail.models import Page


def search(request):
    search_query = request.GET.get("query", None)

    if search_query:
        search_results = Page.objects.live().search(search_query)
    else:
        search_results = Page.objects.none()

    return render(
        request,
        "wtrx/search/search.html",
        {
            "search_query": search_query,
            "search_results": search_results,
        },
    )

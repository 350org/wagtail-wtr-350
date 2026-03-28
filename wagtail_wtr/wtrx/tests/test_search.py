from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from wagtail.models import Page

from wagtail_wtr.wtrx.models import ContentPage, HomePage


class SearchViewTests(TestCase):
    def test_empty_query_returns_no_results(self):
        """GET /search/ with no query renders the template with empty results."""
        response = self.client.get(reverse("search"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "wtrx/search/search.html")
        self.assertIsNone(response.context["search_query"])
        self.assertFalse(response.context["search_results"])

    def test_blank_query_returns_no_results(self):
        """GET /search/?query= with an empty string renders empty results."""
        response = self.client.get(reverse("search"), {"query": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["search_query"], "")
        self.assertFalse(response.context["search_results"])

    def test_query_returns_results_in_context(self):
        """GET /search/?query=... passes search_query in context."""
        response = self.client.get(reverse("search"), {"query": "test"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["search_query"], "test")
        self.assertIn("search_results", response.context)

    def test_search_with_query_returns_200(self):
        """Search view does not raise with the live() filter on an empty DB."""
        response = self.client.get(reverse("search"), {"query": "test"})
        self.assertEqual(response.status_code, 200)


class SearchViewHideFromSearchTests(TestCase):
    """Pages with hide_from_search=True must be excluded from search results.

    The Wagtail SQLite search backend requires explicit indexing via
    update_index. After indexing, a page with hide_from_search=True must
    not appear in the search view's results even if the backend returns it.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-search-test")
        root.add_child(instance=cls.home)

        cls.visible_page = ContentPage(
            title="AlphaVisible Page",
            slug="alphavisible",
            hide_from_search=False,
        )
        cls.home.add_child(instance=cls.visible_page)

        cls.hidden_page = ContentPage(
            title="AlphaHidden Page",
            slug="alphahidden",
            hide_from_search=True,
        )
        cls.home.add_child(instance=cls.hidden_page)

        # Populate the Wagtail search index for both pages.
        call_command("update_index", verbosity=0)

    def _search(self, query):
        response = self.client.get(reverse("search"), {"query": query})
        self.assertEqual(response.status_code, 200)
        return response.context["search_results"]

    def test_visible_page_appears_in_results(self):
        results = self._search("AlphaVisible")
        titles = [p.title for p in results]
        self.assertIn("AlphaVisible Page", titles)

    def test_hidden_page_excluded_from_results(self):
        results = self._search("AlphaHidden")
        titles = [p.title for p in results]
        self.assertNotIn("AlphaHidden Page", titles)

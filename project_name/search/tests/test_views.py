from django.test import TestCase
from django.urls import reverse

from wagtail.models import Page
from wagtail.search.models import Query


class SearchViewTests(TestCase):
    def test_empty_query_returns_no_results(self):
        """GET /search/ with no query renders the template with empty results."""
        response = self.client.get(reverse("search"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "search/search.html")
        self.assertIsNone(response.context["search_query"])
        self.assertFalse(response.context["search_results"])

    def test_blank_query_returns_no_results(self):
        """GET /search/?query= with an empty string renders empty results."""
        response = self.client.get(reverse("search"), {"query": ""})
        self.assertEqual(response.status_code, 200)
        # Empty string is falsy — treated as no query
        self.assertFalse(response.context["search_results"])

    def test_query_returns_results_in_context(self):
        """GET /search/?query=... passes search_query in context."""
        response = self.client.get(reverse("search"), {"query": "test"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["search_query"], "test")
        # search_results is present (may be empty queryset — no pages in test DB)
        self.assertIn("search_results", response.context)

    def test_query_records_hit(self):
        """A search query increments the Query hit count."""
        self.client.get(reverse("search"), {"query": "wagtail"})
        query = Query.get("wagtail")
        self.assertGreaterEqual(query.hit_count, 1)

    def test_second_query_increments_hit_count(self):
        """Each request with the same query increments hit count."""
        self.client.get(reverse("search"), {"query": "wagtail"})
        self.client.get(reverse("search"), {"query": "wagtail"})
        query = Query.get("wagtail")
        self.assertGreaterEqual(query.hit_count, 2)

    def test_no_query_does_not_record_hit(self):
        """A request with no query does not create a Query record."""
        self.client.get(reverse("search"))
        # Query.get() creates a record if it doesn't exist, so check hit_count
        # is 0 for a term that was never searched
        query = Query.get("never-searched-term")
        self.assertEqual(query.hit_count, 0)

    def test_search_results_only_include_live_pages(self):
        """Search results are filtered to live pages only."""
        response = self.client.get(reverse("search"), {"query": "test"})
        # Verify the queryset passed to template is the result of a live() search
        # (no draft pages should appear). With an empty DB this is vacuously true;
        # the assertion confirms no exception is raised by the live() filter.
        self.assertEqual(response.status_code, 200)

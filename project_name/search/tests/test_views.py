from django.test import TestCase
from django.urls import reverse


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

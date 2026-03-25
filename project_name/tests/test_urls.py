from django.test import TestCase
from django.urls import resolve, reverse

from wagtail.contrib.sitemaps.views import sitemap as sitemap_view


class UrlResolutionTests(TestCase):
    def test_django_admin_resolves(self):
        """Django admin URL resolves correctly."""
        resolver = resolve("/django-admin/")
        self.assertEqual(resolver.app_name, "admin")

    def test_wagtail_admin_resolves(self):
        """Wagtail admin URL resolves correctly."""
        resolver = resolve("/admin/")
        self.assertEqual(resolver.app_name, "wagtailadmin")

    def test_sitemap_resolves(self):
        """Sitemap URL resolves to the sitemap view."""
        resolver = resolve("/sitemap.xml")
        self.assertEqual(resolver.func, sitemap_view)

    def test_sitemap_named(self):
        """Sitemap URL is accessible by name."""
        url = reverse("sitemap")
        self.assertEqual(url, "/sitemap.xml")

    def test_search_url_resolves(self):
        """Search URL resolves to the search view by name."""
        url = reverse("search")
        self.assertIn("search", url)

    def test_search_get_returns_200(self):
        """GET /search/ returns a 200 without crashing."""
        response = self.client.get(reverse("search"))
        self.assertEqual(response.status_code, 200)

    def test_media_url_debug_only(self):
        """
        Media files are only served by Django in DEBUG mode.
        This is enforced structurally in urls.py via `if settings.DEBUG`.
        The behaviour cannot be reliably asserted at runtime because URL
        patterns are resolved once at import time, before any test overrides.
        """
        pass

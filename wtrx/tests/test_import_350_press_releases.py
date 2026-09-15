"""
Tests for import_350_press_releases.py's --site wiring: confirm a
country/language site (e.g. --site fr) actually changes the sitemap-index
URL that gets queried, following the same @patch convention as
test_import_350_our_impact.py.
"""

from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import SimpleTestCase

from wtrx.management.commands.import_350_press_releases import fetch_press_release_urls


class TestFetchPressReleaseUrlsSiteUrl(SimpleTestCase):
    def test_uses_the_given_sitemap_index_url(self):
        session = Mock()
        session.get.return_value.text = (
            "<sitemapindex><sitemap><loc>https://350.org/fr/press-release-sitemap.xml</loc>"
            "</sitemap></sitemapindex>"
        )
        session.get.return_value.raise_for_status.return_value = None

        fetch_press_release_urls(session, "https://350.org/fr/sitemap_index.xml")

        first_call_url = session.get.call_args_list[0][0][0]
        self.assertEqual(first_call_url, "https://350.org/fr/sitemap_index.xml")

    def test_defaults_to_main_site_url(self):
        session = Mock()
        session.get.return_value.text = (
            "<sitemapindex><sitemap><loc>https://350.org/press-release-sitemap.xml</loc>"
            "</sitemap></sitemapindex>"
        )
        session.get.return_value.raise_for_status.return_value = None

        fetch_press_release_urls(session, "https://350.org/sitemap_index.xml")

        first_call_url = session.get.call_args_list[0][0][0]
        self.assertEqual(first_call_url, "https://350.org/sitemap_index.xml")


class TestSiteOptionResolution(SimpleTestCase):
    @patch("wtrx.management.commands.import_350_press_releases.resolve_site_base_url")
    def test_invalid_site_value_aborts_with_a_clear_message(self, mock_resolve):
        mock_resolve.side_effect = ValueError(
            "--site should be a URL path segment like 'fr', not 'https://evil.example.com'."
        )
        err = StringIO()
        call_command("import_350_press_releases", "--site=https://evil.example.com", stderr=err)
        self.assertIn("--site should be a URL path segment", err.getvalue())

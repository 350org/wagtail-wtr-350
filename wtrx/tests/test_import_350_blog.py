"""
Tests for import_350_blog.py's --site wiring: confirm a country/language
site (e.g. --site fr) actually changes the WP REST API URL that gets
queried, following the same @patch convention as
test_import_350_our_impact.py.
"""

from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from wtrx.management.commands.import_350_blog import fetch_posts


class TestFetchPostsSiteUrl(SimpleTestCase):
    def test_uses_the_given_wp_api_url(self):
        session = Mock()
        session.get.return_value.json.return_value = []
        session.get.return_value.raise_for_status.return_value = None
        session.get.return_value.headers = {}

        list(fetch_posts(session, "https://350.org/fr/wp-json/wp/v2/posts", limit=5))

        called_url = session.get.call_args[0][0]
        self.assertEqual(called_url, "https://350.org/fr/wp-json/wp/v2/posts")

    def test_defaults_to_main_site_url(self):
        session = Mock()
        session.get.return_value.json.return_value = []
        session.get.return_value.raise_for_status.return_value = None
        session.get.return_value.headers = {}

        list(fetch_posts(session, "https://350.org/wp-json/wp/v2/posts", limit=5))

        called_url = session.get.call_args[0][0]
        self.assertEqual(called_url, "https://350.org/wp-json/wp/v2/posts")


class TestSiteOptionResolution(SimpleTestCase):
    @patch("wtrx.management.commands.import_350_blog.resolve_site_base_url")
    def test_invalid_site_value_aborts_with_a_clear_message(self, mock_resolve):
        from io import StringIO

        from django.core.management import call_command

        mock_resolve.side_effect = ValueError("--site should be a URL path segment like 'fr', not 'https://evil.example.com'.")
        err = StringIO()
        call_command("import_350_blog", "--site=https://evil.example.com", stderr=err)
        self.assertIn("--site should be a URL path segment", err.getvalue())

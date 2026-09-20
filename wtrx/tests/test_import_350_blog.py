"""
Tests for import_350_blog.py's --site wiring: confirm a country/language
site (e.g. --site fr) actually changes the WP REST API URL that gets
queried, following the same @patch convention as
test_import_350_our_impact.py.
"""

from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from wagtail.models import Page

from wtrx.management.commands.import_350_blog import fetch_posts
from wtrx.models import Blogs, HomePage, Post


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


def _fake_wp_post(slug, title="A Post"):
    return {
        "title": {"rendered": title},
        "slug": slug,
        "date_gmt": "2026-01-01T00:00:00",
        "content": {"rendered": "<p>Body</p>"},
        "_embedded": {},
    }


class SkipAuthorsTest(TestCase):
    """
    --skip-authors exists so a run doesn't pay for _author_name()'s extra
    live-page fetch (scraping the guest-contributor byline span) when the
    caller doesn't want author bylines at all.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        home = HomePage(title="Home", slug="home-skip-authors")
        root.add_child(instance=home)
        cls.blogs = Blogs(title="Blog", slug="blog-skip-authors")
        home.add_child(instance=cls.blogs)

    def _run(self, *args):
        with (
            patch("wtrx.management.commands.import_350_blog.verify_site_reachable", return_value=True),
            patch("wtrx.management.commands.import_350_blog._author_name") as mock_author_name,
            patch("wtrx.management.commands.import_350_blog.convert_body", return_value=[]),
            patch(
                "wtrx.management.commands.import_350_blog.yoast_seo_fields_from_api_post",
                return_value=("", ""),
            ),
            patch(
                "wtrx.management.commands.import_350_blog.fetch_posts",
                return_value=[_fake_wp_post("skip-authors-post")],
            ),
        ):
            mock_author_name.return_value = "Scraped Author"
            call_command("import_350_blog", *args, stdout=StringIO(), stderr=StringIO())
            return mock_author_name

    def test_leaves_author_name_blank_on_a_new_post(self):
        self._run("--skip-authors")

        post = Post.objects.child_of(self.blogs).get(slug="skip-authors-post")
        self.assertEqual(post.author_name, "")

    def test_resolves_author_name_by_default(self):
        mock_author_name = self._run()

        mock_author_name.assert_called_once()
        post = Post.objects.child_of(self.blogs).get(slug="skip-authors-post")
        self.assertEqual(post.author_name, "Scraped Author")

    def test_does_not_call_author_name_when_skipped(self):
        mock_author_name = self._run("--skip-authors")

        mock_author_name.assert_not_called()

    def test_update_does_not_overwrite_an_existing_author_name(self):
        existing = Post(
            title="Old title",
            slug="skip-authors-post",
            author_name="Original Byline",
        )
        self.blogs.add_child(instance=existing)

        self._run("--skip-authors", "--update")

        existing.refresh_from_db()
        self.assertEqual(existing.author_name, "Original Byline")
        # Confirm the rest of the update still ran, so this isn't passing
        # because the whole update was skipped.
        self.assertEqual(existing.title, "A Post")

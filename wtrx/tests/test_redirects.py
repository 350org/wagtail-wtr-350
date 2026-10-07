from django.test import SimpleTestCase, TestCase
from wagtail.contrib.redirects.models import Redirect

from wtrx.redirects import merge_query_string


class MergeQueryStringTests(SimpleTestCase):
    def test_appends_to_a_bare_destination(self):
        self.assertEqual(
            merge_query_string("/about/who-we-are/", "form=FUNLBGSMNDU&gclid=test123"),
            "/about/who-we-are/?form=FUNLBGSMNDU&gclid=test123",
        )

    def test_no_query_string_leaves_destination_untouched(self):
        self.assertEqual(merge_query_string("/about/who-we-are/", ""), "/about/who-we-are/")

    def test_destination_parameter_wins_over_incoming(self):
        self.assertEqual(
            merge_query_string("/donate/?form=FUNABC", "form=FUNXYZ&utm_source=email"),
            "/donate/?form=FUNABC&utm_source=email",
        )

    def test_fragment_stays_after_the_query(self):
        self.assertEqual(merge_query_string("/about/#team", "gclid=1"), "/about/?gclid=1#team")

    def test_absolute_destination(self):
        self.assertEqual(
            merge_query_string("https://act.350.org/sign/x/", "akid=1.2.3&source=email"),
            "https://act.350.org/sign/x/?akid=1.2.3&source=email",
        )

    def test_blank_and_repeated_values_survive(self):
        self.assertEqual(merge_query_string("/a/", "x=&y=1&y=2"), "/a/?x=&y=1&y=2")


class QueryPreservingRedirectMiddlewareTests(TestCase):
    def test_query_string_is_carried_to_the_destination(self):
        Redirect.add_redirect("/old-about", "/about/who-we-are/")
        response = self.client.get("/old-about/?form=FUNLBGSMNDU&gclid=test123")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/about/who-we-are/?form=FUNLBGSMNDU&gclid=test123")

    def test_redirect_without_a_query_string_is_unchanged(self):
        Redirect.add_redirect("/old-about", "/about/who-we-are/")
        response = self.client.get("/old-about/")
        self.assertEqual(response["Location"], "/about/who-we-are/")

    def test_temporary_redirect_keeps_its_status(self):
        Redirect.add_redirect("/old-about", "/about/who-we-are/", is_permanent=False)
        response = self.client.get("/old-about/?utm_source=email")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/about/who-we-are/?utm_source=email")

    def test_query_specific_redirect_is_served_as_stored(self):
        """A redirect stored *with* a query string maps that one URL; nothing is carried over."""
        Redirect.add_redirect("/old-about?campaign=spring", "/spring/")
        response = self.client.get("/old-about/?campaign=spring")
        self.assertEqual(response["Location"], "/spring/")

    def test_unmatched_path_still_404s(self):
        response = self.client.get("/no-such-page/?gclid=test123")
        self.assertEqual(response.status_code, 404)

"""
Tests for wtrx.management.commands._wp_content_utils:

- Cloudflare email-obfuscation handling (_decode_cf_email / _unmask_cf_emails).
  Cloudflare's "Email Address Obfuscation" marks the obfuscated text with
  class="__cf_email__" data-cfemail="<hex>", but which element carries that
  mark depends on the original markup: a separate <span> nested inside the
  <a> when the email text wasn't already the anchor's sole content, or
  directly on the <a> itself (no span) when it was. A real 350.org press
  release uses the latter shape and was left completely unfixed by an
  earlier version of _unmask_cf_emails that only looked for a <span>.
- Country/language site base-URL resolution (resolve_site_base_url /
  verify_site_reachable), used by both import_350_blog.py and
  import_350_press_releases.py's --site option.
- Blogs-target resolution by path (resolve_blogs_target /
  _find_page_by_path), needed because Page.slug is only unique among
  siblings, not site-wide -- a country/region sub-home's own Blogs child
  can share a slug with an unrelated page elsewhere in the tree.
"""

from unittest.mock import Mock

from bs4 import BeautifulSoup
from django.test import SimpleTestCase, TestCase
from wagtail.models import Page, Site

from wtrx.management.commands._wp_content_utils import (
    _decode_cf_email,
    _find_page_by_path,
    _unmask_cf_emails,
    resolve_blogs_target,
    resolve_site_base_url,
    verify_site_reachable,
)


def _cf_encode(email, key=0x2B):
    return format(key, "02x") + "".join(format(ord(c) ^ key, "02x") for c in email)


class TestDecodeCfEmail(SimpleTestCase):
    def test_round_trips(self):
        encoded = _cf_encode("media@350.org")
        self.assertEqual(_decode_cf_email(encoded), "media@350.org")

    def test_matches_real_world_hex(self):
        # Captured from a live 350.org press release page.
        self.assertEqual(
            _decode_cf_email("1c75707d727b326d6975767d72735c2f292c32736e7b"),
            "ilang.quijano@350.org",
        )


class TestUnmaskCfEmails(SimpleTestCase):
    def test_nested_span_shape(self):
        """class/data-cfemail on a <span> nested inside the <a>."""
        encoded = _cf_encode("media@350.org")
        html = (
            f'<p>Contact <a href="/cdn-cgi/l/email-protection#{encoded}">'
            f'<span class="__cf_email__" data-cfemail="{encoded}">[email&#160;protected]</span>'
            f"</a></p>"
        )
        soup = BeautifulSoup(html, "html.parser")
        _unmask_cf_emails(soup)
        anchor = soup.find("a")
        self.assertEqual(anchor["href"], "mailto:media@350.org")
        self.assertEqual(anchor.get_text(), "media@350.org")
        self.assertIsNone(soup.find("span"))

    def test_attributes_directly_on_anchor_shape(self):
        """class/data-cfemail on the <a> itself, no nested <span> at all —
        the shape that silently defeated the span-only lookup."""
        encoded = "1c75707d727b326d6975767d72735c2f292c32736e7b"
        html = (
            f'<p>Media Campaigner, <a href="/cdn-cgi/l/email-protection" '
            f'class="__cf_email__" data-cfemail="{encoded}">[email&#160;protected]</a>, '
            f"+639175810934</p>"
        )
        soup = BeautifulSoup(html, "html.parser")
        _unmask_cf_emails(soup)
        anchor = soup.find("a")
        self.assertEqual(anchor["href"], "mailto:ilang.quijano@350.org")
        self.assertEqual(anchor.get_text(), "ilang.quijano@350.org")

    def test_missing_data_cfemail_is_left_alone(self):
        html = '<p><span class="__cf_email__">[email&#160;protected]</span></p>'
        soup = BeautifulSoup(html, "html.parser")
        _unmask_cf_emails(soup)
        self.assertIsNotNone(soup.find("span", class_="__cf_email__"))

    def test_invalid_hex_is_left_alone(self):
        html = '<p><span class="__cf_email__" data-cfemail="zz">[email&#160;protected]</span></p>'
        soup = BeautifulSoup(html, "html.parser")
        _unmask_cf_emails(soup)
        self.assertIsNotNone(soup.find("span", class_="__cf_email__"))

    def test_no_email_markup_is_a_no_op(self):
        html = "<p>Nothing to see here.</p>"
        soup = BeautifulSoup(html, "html.parser")
        _unmask_cf_emails(soup)
        self.assertEqual(str(soup), html)


class TestResolveSiteBaseUrl(SimpleTestCase):
    def test_blank_resolves_to_main_site(self):
        self.assertEqual(resolve_site_base_url(""), "https://350.org")

    def test_site_segment_resolves_to_subsite(self):
        self.assertEqual(resolve_site_base_url("fr"), "https://350.org/fr")

    def test_strips_stray_slashes(self):
        self.assertEqual(resolve_site_base_url("/fr/"), "https://350.org/fr")

    def test_full_url_by_mistake_raises(self):
        with self.assertRaises(ValueError):
            resolve_site_base_url("https://evil.example.com")

    def test_leading_dot_raises(self):
        with self.assertRaises(ValueError):
            resolve_site_base_url("../etc")


class TestVerifySiteReachable(SimpleTestCase):
    def test_true_when_wp_v2_namespace_present(self):
        session = Mock()
        session.get.return_value.json.return_value = {"namespaces": ["oembed/1.0", "wp/v2"]}
        session.get.return_value.raise_for_status.return_value = None
        self.assertTrue(verify_site_reachable(session, "https://350.org/fr"))
        session.get.assert_called_once_with("https://350.org/fr/wp-json/", timeout=15)

    def test_false_when_namespace_missing(self):
        session = Mock()
        session.get.return_value.json.return_value = {"namespaces": ["oembed/1.0"]}
        session.get.return_value.raise_for_status.return_value = None
        self.assertFalse(verify_site_reachable(session, "https://350.org/nowhere"))

    def test_false_on_request_exception(self):
        import requests

        session = Mock()
        session.get.side_effect = requests.exceptions.ConnectionError("boom")
        self.assertFalse(verify_site_reachable(session, "https://350.org/nowhere"))

    def test_false_on_non_json_response(self):
        session = Mock()
        session.get.return_value.raise_for_status.return_value = None
        session.get.return_value.json.side_effect = ValueError("not json")
        self.assertFalse(verify_site_reachable(session, "https://350.org/nowhere"))


class TestResolveBlogsTargetByPath(TestCase):
    """
    Page.slug is only unique among siblings, not site-wide: a France
    sub-home's "press-releases" Blogs child can share a slug with the
    top-level English "press-releases" Blogs page. A bare-slug --target
    can't disambiguate that; a path can.
    """

    @classmethod
    def setUpTestData(cls):
        from wtrx.models import Blogs, ContentPage, HomePage

        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Test Site", slug="test-home-path")
        root.add_child(instance=cls.home)

        # Repoint the migration-created default Site rather than adding a
        # second is_default_site=True row -- Site.save() has no uniqueness
        # override for that flag, so
        # Site.objects.filter(is_default_site=True).first() (what
        # _find_page_by_path relies on) would otherwise nondeterministically
        # pick whichever of the two rows sorts first, not necessarily this
        # test's own tree.
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.hostname = "path-test.localhost"
        site.save()

        cls.top_blogs = Blogs(title="Press Releases", slug="press-releases")
        cls.home.add_child(instance=cls.top_blogs)

        cls.france = HomePage(title="France", slug="france")
        cls.home.add_child(instance=cls.france)

        cls.france_blogs = Blogs(title="Press Releases (France)", slug="press-releases")
        cls.france.add_child(instance=cls.france_blogs)

        cls.france_about = ContentPage(title="About", slug="about")
        cls.france.add_child(instance=cls.france_about)

    def setUp(self):
        self.stderr = Mock()
        self.style = Mock(ERROR=lambda msg: msg)

    def test_path_disambiguates_a_colliding_slug(self):
        result = resolve_blogs_target(self.stderr, self.style, "france/press-releases")
        self.assertEqual(result.pk, self.france_blogs.pk)

    def test_bare_slug_lookup_is_unchanged_and_can_still_be_ambiguous(self):
        # Existing behavior, deliberately preserved: a bare slug goes
        # through the old Blogs.objects.filter(slug=...).first() lookup,
        # which doesn't know or care that two Blogs pages share this slug
        # -- it just returns whichever one comes back first. This is
        # exactly the ambiguity --target <path> exists to let you avoid.
        result = resolve_blogs_target(self.stderr, self.style, "press-releases")
        self.assertIn(result.pk, {self.top_blogs.pk, self.france_blogs.pk})

    def test_nonexistent_path_reports_a_clear_error(self):
        result = resolve_blogs_target(self.stderr, self.style, "france/nonexistent")
        self.assertIsNone(result)
        self.stderr.write.assert_called_once_with("No page found at path 'france/nonexistent'.")

    def test_path_to_a_non_blogs_page_reports_a_clear_error(self):
        result = resolve_blogs_target(self.stderr, self.style, "france/about")
        self.assertIsNone(result)
        self.stderr.write.assert_called_once_with(
            "Page at path 'france/about' is a ContentPage, not a Blogs page."
        )

    def test_find_page_by_path_returns_specific_subtype(self):
        page = _find_page_by_path("france/press-releases")
        self.assertEqual(page.pk, self.france_blogs.pk)
        self.assertIsInstance(page, type(self.france_blogs))

    def test_find_page_by_path_strips_slashes(self):
        page = _find_page_by_path("/france/press-releases/")
        self.assertEqual(page.pk, self.france_blogs.pk)

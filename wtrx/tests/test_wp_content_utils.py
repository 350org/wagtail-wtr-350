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
- Video embeds (video_embed_url / convert_body): YouTube and Vimeo player
  iframes become "video" blocks rather than being dropped with the other
  disallowed tags -- including the classic-editor shape where the iframe
  sits inside a <p>.
"""

from unittest.mock import Mock

from bs4 import BeautifulSoup
from django.test import SimpleTestCase, TestCase
from wagtail.models import Page, Site

from wtrx.management.commands._wp_content_utils import (
    _decode_cf_email,
    convert_body,
    _find_page_by_path,
    _unmask_cf_emails,
    resolve_blogs_target,
    resolve_site_base_url,
    verify_site_reachable,
    video_embed_url,
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


class TestVideoEmbedUrl(SimpleTestCase):
    def test_youtube_embed_becomes_watch_url(self):
        self.assertEqual(
            video_embed_url("https://www.youtube.com/embed/s5kg1oOq9tY?si=6CdZwRrleJpVWfiO"),
            "https://www.youtube.com/watch?v=s5kg1oOq9tY",
        )

    def test_youtube_nocookie_protocol_relative_and_start_time(self):
        self.assertEqual(
            video_embed_url("//www.youtube-nocookie.com/embed/abc123DEF_-?rel=0&amp;start=42"),
            "https://www.youtube.com/watch?v=abc123DEF_-&t=42",
        )

    def test_vimeo_player_becomes_page_url(self):
        self.assertEqual(
            video_embed_url("https://player.vimeo.com/video/405768387?dnt=1&amp;app_id=122963"),
            "https://vimeo.com/405768387",
        )

    def test_vimeo_private_hash_is_kept(self):
        self.assertEqual(
            video_embed_url("https://player.vimeo.com/video/405768387?h=ab12cd"),
            "https://vimeo.com/405768387/ab12cd",
        )

    def test_other_iframes_are_unsupported(self):
        self.assertIsNone(video_embed_url("https://www.facebook.com/plugins/post.php?href=x"))
        self.assertIsNone(video_embed_url(""))


class TestConvertBodyVideos(SimpleTestCase):
    def _convert(self, content_html):
        blocks = convert_body(content_html, session=None, stdout=Mock())
        return [(b["type"], b["value"]) for b in blocks]

    def test_iframe_inside_paragraph_becomes_video_block(self):
        # The shape of https://350.org/350-name/.
        blocks = self._convert(
            "<p><strong>Here's a video:</strong></p>"
            '<p style="text-align: center;"><iframe src="https://www.youtube.com/embed/s5kg1oOq9tY?si=x">'
            "</iframe></p><p>After.</p>"
        )
        self.assertEqual(
            blocks,
            [
                ("text", "<p><strong>Here's a video:</strong></p>"),
                ("video", {"embed_url": "https://www.youtube.com/watch?v=s5kg1oOq9tY", "caption": ""}),
                ("text", "<p>After.</p>"),
            ],
        )

    def test_block_editor_embed_figure(self):
        blocks = self._convert(
            '<figure class="wp-block-embed is-provider-vimeo"><div class="wp-block-embed__wrapper">'
            '<iframe src="https://player.vimeo.com/video/405768387?dnt=1"></iframe></div></figure>'
        )
        self.assertEqual(blocks, [("video", {"embed_url": "https://vimeo.com/405768387", "caption": ""})])

    def test_paragraph_text_beside_iframe_is_kept(self):
        blocks = self._convert('<p>Watch: <iframe src="https://www.youtube.com/embed/s5kg1oOq9tY"></iframe></p>')
        self.assertEqual([t for t, _ in blocks], ["text", "video"])
        self.assertIn("Watch:", blocks[0][1])

    def test_unsupported_iframe_is_still_dropped(self):
        stdout = Mock()
        blocks = convert_body(
            '<p>Hi</p><iframe src="https://www.facebook.com/plugins/post.php"></iframe>', session=None, stdout=stdout
        )
        self.assertEqual([b["type"] for b in blocks], ["text"])
        self.assertIn("unsupported embed", stdout.write.call_args[0][0])

"""
Tests for _video_value() in the import_350_our_impact management command --
pins the branch that gives oEmbed-unsupported direct video-file links (all
real cases are 350.org's own Widen CDN .mp4 links) a self-hosted
wagtailmedia Media fallback instead of being silently dropped.
"""

from io import StringIO
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from wtrx.management.commands.import_350_our_impact import _video_value


def _container(html):
    return BeautifulSoup(html, "html.parser")


class VideoValueTest(SimpleTestCase):
    def test_returns_an_embed_url_for_an_oembed_supported_youtube_url(self):
        container = _container(
            '<div class="embed-section"><div class="video-container">'
            '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"></iframe>'
            "</div></div>"
        )
        out = StringIO()

        value = _video_value(container, session=None, stdout=out, dry_run=False, context="year video")

        self.assertEqual(
            value,
            {
                "embed_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "media_file": None,
                "caption": "",
            },
        )
        self.assertEqual(out.getvalue(), "")

    def test_returns_an_embed_url_for_an_oembed_supported_vimeo_url(self):
        container = _container(
            '<div class="video-container">'
            '<iframe src="https://player.vimeo.com/video/12345"></iframe>'
            "</div>"
        )
        out = StringIO()

        value = _video_value(container, session=None, stdout=out, dry_run=False, context="year video")

        self.assertEqual(
            value,
            {"embed_url": "https://player.vimeo.com/video/12345", "media_file": None, "caption": ""},
        )
        self.assertEqual(out.getvalue(), "")

    @patch("wtrx.management.commands.import_350_our_impact._safe_download_video")
    def test_downloads_and_returns_a_media_file_for_a_direct_widen_mp4_link(self, mock_download):
        mock_download.return_value.pk = 42
        container = _container(
            '<div class="video-container">'
            '<iframe src="https://350org.widen.net/view/video/abc123/broll.mp4?u=xyz"></iframe>'
            "</div>"
        )
        out = StringIO()
        session = object()

        value = _video_value(container, session=session, stdout=out, dry_run=False, context="year video")

        self.assertEqual(value, {"embed_url": "", "media_file": 42, "caption": ""})
        mock_download.assert_called_once_with(
            session, "https://350org.widen.net/view/video/abc123/broll.mp4?u=xyz", out, dry_run=False
        )
        self.assertEqual(out.getvalue(), "")

    @patch("wtrx.management.commands.import_350_our_impact._safe_download_video")
    def test_matches_direct_file_extensions_other_than_mp4(self, mock_download):
        mock_download.return_value.pk = 1
        for ext in ("webm", "mov", "ogg"):
            with self.subTest(ext=ext):
                container = _container(
                    f'<div class="video-container"><iframe src="https://350org.widen.net/x.{ext}">'
                    "</iframe></div>"
                )
                out = StringIO()
                value = _video_value(container, session=None, stdout=out, dry_run=False, context="year video")
                self.assertEqual(value["media_file"], 1)

    @patch("wtrx.management.commands.import_350_our_impact._safe_download_video")
    def test_returns_none_when_the_direct_file_download_fails(self, mock_download):
        mock_download.return_value = None
        container = _container(
            '<div class="video-container">'
            '<iframe src="https://350org.widen.net/view/video/abc123/broll.mp4"></iframe>'
            "</div>"
        )
        out = StringIO()

        value = _video_value(container, session=None, stdout=out, dry_run=False, context="year video")

        self.assertIsNone(value)

    def test_returns_none_and_warns_for_a_genuinely_unsupported_non_file_url(self):
        container = _container(
            '<div class="video-container">'
            '<iframe src="https://example-video-host.test/embed/xyz"></iframe>'
            "</div>"
        )
        out = StringIO()

        value = _video_value(
            container, session=None, stdout=out, dry_run=False, context="victory item 'A Title'"
        )

        self.assertIsNone(value)
        self.assertIn("WARNING: unsupported video provider for victory item 'A Title'", out.getvalue())
        self.assertIn("https://example-video-host.test/embed/xyz", out.getvalue())

    def test_returns_none_when_there_is_no_iframe(self):
        container = _container('<div class="video-container"></div>')
        out = StringIO()

        value = _video_value(container, session=None, stdout=out, dry_run=False, context="year video")

        self.assertIsNone(value)
        self.assertEqual(out.getvalue(), "")

    def test_returns_none_when_the_iframe_has_no_src(self):
        container = _container('<div class="video-container"><iframe></iframe></div>')
        out = StringIO()

        value = _video_value(container, session=None, stdout=out, dry_run=False, context="year video")

        self.assertIsNone(value)
        self.assertEqual(out.getvalue(), "")


class DownloadVideoTest(SimpleTestCase):
    """download_video() itself -- dedup lookup and dry-run need a DB, so those
    two branches are exercised via _video_value()'s mocked-out unit tests
    above; here we only check the no-url short circuit, which needs no DB."""

    def test_returns_none_for_an_empty_url(self):
        from wtrx.management.commands.import_350_our_impact import download_video

        out = StringIO()
        self.assertIsNone(download_video(session=None, url="", stdout=out))
        self.assertEqual(out.getvalue(), "")


_WIDEN_PLAYER_HTML = """
<!doctype html><html><head><title>video.mp4</title>
<script id="bootstrap-data">window.bootstrapData = {
  "previews": {
    "files": [
      {"label": "1080p", "source": "https://cdn.example/1080p.mp4?Sig=a"},
      {"label": "720p", "source": "https://cdn.example/720p.mp4?Sig=b"},
      {"label": "480p", "source": "https://cdn.example/480p.mp4?Sig=c"},
      {"label": "360p", "source": "https://cdn.example/360p.mp4?Sig=d"}
    ]
  }
};</script></head><body><div id="root"></div></body></html>
"""


class ResolveWidenVideoDownloadUrlTest(SimpleTestCase):
    def test_prefers_720p_when_available(self):
        from wtrx.management.commands.import_350_our_impact import _resolve_widen_video_download_url

        self.assertEqual(
            _resolve_widen_video_download_url(_WIDEN_PLAYER_HTML),
            "https://cdn.example/720p.mp4?Sig=b",
        )

    def test_falls_back_down_the_preference_list_when_720p_is_missing(self):
        from wtrx.management.commands.import_350_our_impact import _resolve_widen_video_download_url

        html = _WIDEN_PLAYER_HTML.replace(
            '{"label": "720p", "source": "https://cdn.example/720p.mp4?Sig=b"},', ""
        )
        self.assertEqual(
            _resolve_widen_video_download_url(html),
            "https://cdn.example/480p.mp4?Sig=c",
        )

    def test_falls_back_to_the_first_file_when_no_preferred_label_matches(self):
        from wtrx.management.commands.import_350_our_impact import _resolve_widen_video_download_url

        html = """
        <script id="bootstrap-data">window.bootstrapData = {
          "previews": {"files": [{"label": "4k", "source": "https://cdn.example/4k.mp4"}]}
        };</script>
        """
        self.assertEqual(_resolve_widen_video_download_url(html), "https://cdn.example/4k.mp4")

    def test_returns_none_when_there_is_no_bootstrap_data(self):
        from wtrx.management.commands.import_350_our_impact import _resolve_widen_video_download_url

        self.assertIsNone(_resolve_widen_video_download_url("<html><body>nothing here</body></html>"))

    def test_returns_none_when_bootstrap_data_is_malformed(self):
        from wtrx.management.commands.import_350_our_impact import _resolve_widen_video_download_url

        html = '<script id="bootstrap-data">window.bootstrapData = {not json};</script>'
        self.assertIsNone(_resolve_widen_video_download_url(html))

    def test_returns_none_when_previews_has_no_files(self):
        from wtrx.management.commands.import_350_our_impact import _resolve_widen_video_download_url

        html = '<script id="bootstrap-data">window.bootstrapData = {"previews": {}};</script>'
        self.assertIsNone(_resolve_widen_video_download_url(html))

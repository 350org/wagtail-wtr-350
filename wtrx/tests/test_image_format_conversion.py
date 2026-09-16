"""
Tests for WAGTAILIMAGES_FORMAT_CONVERSIONS (settings/base.py) and the two
base.html call sites deliberately pinned away from it.

Prompted by a PageSpeed Insights "Improve image delivery" flag: PNG-sourced
renditions with no explicit format in their filter spec (e.g. "fill-640x360")
were served as PNG, several times larger than the same content as WebP.
Wagtail's own default_conversions dict (wagtail/images/models.py) has no
entry for a PNG source, so it falls through unchanged unless overridden here.

og:image/twitter:image and the favicon are pinned to an explicit format in
base.html itself (format-jpeg / format-png) since their consumer isn't a
browser rendering our own page -- social link-preview crawlers and
browser/OS favicon handling need broader format support than "renders in an
evergreen browser".
"""

from django.conf import settings
from django.test import Client, TestCase
from wagtail.images.tests.utils import get_test_image_file
from wagtail.models import Page, Site

from wtrx.images import CustomImage
from wtrx.models import HomePage
from wtrx.site_settings import BrandingSEOSettings


class TestFormatConversionSetting(TestCase):
    def test_png_sources_default_to_webp(self):
        self.assertEqual(settings.WAGTAILIMAGES_FORMAT_CONVERSIONS.get("png"), "webp")


class TestGenericRenditionsOfPngSourcesAreWebp(TestCase):
    def test_fill_rendition_of_a_png_source_is_webp(self):
        image = CustomImage.objects.create(
            title="Screenshot",
            file=get_test_image_file(filename="Screenshot-test.png"),
            description="A screenshot",
        )
        rendition = image.get_rendition("fill-640x360")
        self.assertTrue(rendition.file.name.endswith(".webp"))


class TestBaseHtmlPinnedImageFormats(TestCase):
    """
    Full-page renders (not isolated template snippets) so these exercise the
    actual base.html markup a browser/crawler would see.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Format Pin Test", slug="format-pin-test")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="format-pin-test.localhost",
            port=80,
            root_page=cls.home,
            site_name="Format Pin Test",
        )
        cls.branding, _ = BrandingSEOSettings.objects.get_or_create(site=cls.site)
        cls.branding.default_meta_image = CustomImage.objects.create(
            title="Meta image",
            file=get_test_image_file(filename="meta-image.png", size=(1600, 900)),
            description="Meta image",
        )
        cls.branding.favicon = CustomImage.objects.create(
            title="Favicon",
            file=get_test_image_file(filename="favicon-source.png", size=(64, 64)),
            description="Favicon",
        )
        cls.branding.save()

    def setUp(self):
        self.client = Client(HTTP_HOST=self.site.hostname)

    def _content(self):
        return self.client.get(self.home.url).content.decode()

    def test_og_image_from_a_png_source_is_jpg_not_webp(self):
        content = self._content()
        self.assertIn('property="og:image"', content)
        self.assertRegex(content, r'property="og:image" content="[^"]+\.jpg"')
        self.assertNotIn(".webp", content)

    def test_favicon_from_a_png_source_stays_png_not_webp(self):
        content = self._content()
        self.assertRegex(content, r'rel="icon" href="[^"]+\.png"')
        self.assertNotIn(".webp", content)

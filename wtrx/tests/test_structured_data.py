"""
Tests for wtrx.templatetags.wtrx_tags.organization_structured_data.

Builds a site-wide Organization JSON-LD <script> tag from existing
Branding & SEO / Social settings data (see AGENTS.md's wagtail-seo
comparison note) — no dedicated structured-data fields.
"""

import json

from django.test import Client, RequestFactory, TestCase
from wagtail.images.tests.utils import get_test_image_file
from wagtail.models import Page, Site

from wtrx.images import CustomImage
from wtrx.models import ContentPage, HomePage
from wtrx.site_settings import BrandingSEOSettings, SocialSettings
from wtrx.templatetags.wtrx_tags import organization_structured_data


class TestOrganizationStructuredData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.get(is_default_site=True)
        cls.site.site_name = "Test Org"
        cls.site.save()
        cls.branding, _ = BrandingSEOSettings.objects.get_or_create(site=cls.site)
        cls.social, _ = SocialSettings.objects.get_or_create(site=cls.site)

    def setUp(self):
        self.factory = RequestFactory()

    def _render(self, request=None):
        context = {"request": request} if request else {}
        html = organization_structured_data(context)
        return html

    def _data(self, html):
        prefix = '<script type="application/ld+json">'
        suffix = "</script>"
        self.assertTrue(html.startswith(prefix))
        self.assertTrue(html.endswith(suffix))
        return json.loads(html[len(prefix) : -len(suffix)])

    def test_no_request_returns_empty_string(self):
        self.assertEqual(self._render(request=None), "")

    def test_base_fields(self):
        request = self.factory.get("/", HTTP_HOST=self.site.hostname)
        data = self._data(self._render(request))
        self.assertEqual(data["@context"], "https://schema.org")
        self.assertEqual(data["@type"], "Organization")
        self.assertEqual(data["name"], "Test Org")
        self.assertTrue(data["url"].endswith("/"))

    def test_falls_back_to_hostname_when_site_name_blank(self):
        self.site.site_name = ""
        self.site.save()
        request = self.factory.get("/", HTTP_HOST=self.site.hostname)
        data = self._data(self._render(request))
        self.assertEqual(data["name"], self.site.hostname)
        self.site.site_name = "Test Org"
        self.site.save()

    def test_description_included_when_configured(self):
        self.branding.site_description = "A test organization."
        self.branding.save()
        request = self.factory.get("/", HTTP_HOST=self.site.hostname)
        data = self._data(self._render(request))
        self.assertEqual(data["description"], "A test organization.")
        self.branding.site_description = ""
        self.branding.save()

    def test_description_omitted_when_blank(self):
        self.branding.site_description = ""
        self.branding.save()
        request = self.factory.get("/", HTTP_HOST=self.site.hostname)
        data = self._data(self._render(request))
        self.assertNotIn("description", data)

    def test_logo_omitted_when_not_configured(self):
        request = self.factory.get("/", HTTP_HOST=self.site.hostname)
        data = self._data(self._render(request))
        self.assertNotIn("logo", data)

    def test_same_as_from_social_links(self):
        self.social.social_links = [
            ("link", {"platform": "facebook", "url": "https://facebook.com/testorg"}),
            ("link", {"platform": "twitter", "url": "https://twitter.com/testorg"}),
        ]
        self.social.save()
        request = self.factory.get("/", HTTP_HOST=self.site.hostname)
        data = self._data(self._render(request))
        self.assertEqual(
            data["sameAs"],
            ["https://facebook.com/testorg", "https://twitter.com/testorg"],
        )
        self.social.social_links = []
        self.social.save()

    def test_same_as_omitted_when_no_social_links(self):
        self.social.social_links = []
        self.social.save()
        request = self.factory.get("/", HTTP_HOST=self.site.hostname)
        data = self._data(self._render(request))
        self.assertNotIn("sameAs", data)

    def test_html_special_characters_are_escaped(self):
        """
        The description is editor-controlled — must not allow it to break
        out of the <script> tag if it contains "</script>" or similar.
        """
        self.branding.site_description = "Stop climate change</script><script>alert(1)</script>"
        self.branding.save()
        request = self.factory.get("/", HTTP_HOST=self.site.hostname)
        html = self._render(request)
        self.assertNotIn("</script><script>", html)
        data = self._data(html)
        self.assertIn("alert(1)", data["description"])
        self.branding.site_description = ""
        self.branding.save()


class TestBaseTemplateSeoTagsRender(TestCase):
    """
    End-to-end check that base.html actually renders the canonical link,
    twitter:site meta tag, and Organization JSON-LD script for a real page
    response — not just that the pieces work in isolation.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="seo-render-home")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="seo-render-test.localhost",
            port=80,
            root_page=cls.home,
            site_name="SEO Render Test",
        )
        cls.page = ContentPage(title="About", slug="about")
        cls.home.add_child(instance=cls.page)

        cls.branding, _ = BrandingSEOSettings.objects.get_or_create(site=cls.site)
        cls.social, _ = SocialSettings.objects.get_or_create(site=cls.site)
        cls.social.social_links = [
            ("link", {"platform": "twitter", "url": "https://twitter.com/testorg"})
        ]
        cls.social.save()

    def setUp(self):
        self.client = Client(HTTP_HOST="seo-render-test.localhost")

    def test_canonical_link_defaults_to_page_url(self):
        response = self.client.get(self.page.url)
        content = response.content.decode()
        self.assertIn(f'<link rel="canonical" href="{self.page.full_url}"', content)

    def test_canonical_link_uses_override(self):
        self.page.canonical_url = "https://example.com/canonical-elsewhere/"
        self.page.save()
        response = self.client.get(self.page.url)
        content = response.content.decode()
        self.assertIn(
            '<link rel="canonical" href="https://example.com/canonical-elsewhere/"',
            content,
        )
        self.page.canonical_url = ""
        self.page.save()

    def test_twitter_site_meta_tag_derived_from_social_links(self):
        """
        twitter:site is derived from SocialSettings.social_links's "twitter"
        entry (see SocialSettings.twitter_handle) — no separate
        BrandingSEOSettings.twitter_site field any more.
        """
        response = self.client.get(self.page.url)
        content = response.content.decode()
        self.assertIn('<meta name="twitter:site" content="@testorg" />', content)

    def test_organization_json_ld_present(self):
        response = self.client.get(self.page.url)
        content = response.content.decode()
        self.assertIn('<script type="application/ld+json">', content)
        self.assertIn('"@type": "Organization"', content)

    def test_og_image_url_is_absolute_and_not_polluted_by_page_path(self):
        """
        Regression test: og:image/twitter:image used to be built from
        {{ request.build_absolute_uri }}{{ og_img.url }} — build_absolute_uri
        called with no argument returns the *current page's* URL (e.g.
        http://host/about/), so concatenating the image's root-relative URL
        produced http://host/about//media/images/foo.jpg, a 404. Only the
        homepage ("/") ever produced a working URL by coincidence. This page
        is deliberately not at the root so the bug would reproduce here.
        """
        image = CustomImage.objects.create(title="Meta image", file=get_test_image_file())
        self.branding.default_meta_image = image
        self.branding.save()

        response = self.client.get(self.page.url)
        content = response.content.decode()

        self.assertNotIn(f"{self.page.full_url}/media/", content)
        self.assertNotIn(f"{self.page.full_url}//media/", content)
        self.assertIn(f'content="http://{self.site.hostname}/media/', content)

        self.branding.default_meta_image = None
        self.branding.save()

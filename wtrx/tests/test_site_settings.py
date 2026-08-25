"""
Tests for wtrx.site_settings.

- TestDonateBlockSuggestedAmounts: DonateBlock's resolution of the ActBlue
  integration config. donation_suggested_amounts parsing used to be a
  property on IntegrationSettings; it now lives in DonateBlock.get_context()
  (see wtrx/blocks/__init__.py), reading the enabled "actblue" integration
  entry from IntegrationSettings.integrations.
- TestNavigationSettingsResolvedForPage: NavigationSettings.resolved_for_page(),
  which picks the most specific navigation_overrides entry (by root_page) for
  a given page, falling back to the site default navigation.
- TestRegionalLabelRendersInHeader: the region badge beside the logo, driven by
  regional_label on a navigation override (or site-wide on NavigationSettings),
  plus the logo lockup's link target.
- TestHeaderLogoRendering: the header logo's hover treatment, a CSS filter
  that works on any logo format.
"""

import base64

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, TestCase
from wagtail.models import Page, Site

from wtrx.blocks import DonateBlock
from wtrx.images import CustomImage
from wtrx.models import ContentPage, HomePage
from wtrx.site_settings import (
    BrandingSEOSettings,
    IntegrationSettings,
    NavigationSettings,
)

# Minimal fixtures for TestHeaderLogoRendering — one of each format, to pin
# down that the hover treatment does not depend on which was uploaded.
SVG_LOGO = (
    b'<svg width="95" height="41" viewBox="0 0 95 41" fill="none" '
    b'xmlns="http://www.w3.org/2000/svg">'
    b'<path d="M0 0H95V41H0Z" fill="#0F81E9"/></svg>'
)
PNG_PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    "IQAAAABJRU5ErkJggg=="
)


class TestDonateBlockSuggestedAmounts(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.get(is_default_site=True)
        cls.integration, _ = IntegrationSettings.objects.get_or_create(
            site=cls.site,
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.block = DonateBlock()

    def _set_amounts(self, value):
        self.integration.integrations = [
            (
                "actblue",
                {
                    "enabled": True,
                    "base_url": "",
                    "suggested_amounts": value,
                    "default_recurring": False,
                },
            )
        ]
        self.integration.save()

    def _amounts_list(self):
        value = self.block.to_python({})
        request = self.factory.get("/")
        ctx = self.block.get_context(value, parent_context={"request": request})
        return ctx["donation_suggested_amounts_list"]

    def test_parses_comma_separated_integers(self):
        self._set_amounts("10,25,50,100")
        self.assertEqual(self._amounts_list(), [10, 25, 50, 100])

    def test_handles_whitespace(self):
        self._set_amounts(" 10 , 25 , 50 ")
        self.assertEqual(self._amounts_list(), [10, 25, 50])

    def test_empty_string_returns_empty_list(self):
        self._set_amounts("")
        self.assertEqual(self._amounts_list(), [])

    def test_blank_returns_empty_list(self):
        self._set_amounts("   ")
        self.assertEqual(self._amounts_list(), [])

    def test_invalid_values_return_empty_list(self):
        self._set_amounts("abc,def")
        self.assertEqual(self._amounts_list(), [])

    def test_single_value(self):
        self._set_amounts("50")
        self.assertEqual(self._amounts_list(), [50])

    def test_trailing_comma_ignored(self):
        self._set_amounts("10,25,")
        self.assertEqual(self._amounts_list(), [10, 25])

    def test_no_actblue_config_returns_empty_list(self):
        self.integration.integrations = []
        self.integration.save()
        self.assertEqual(self._amounts_list(), [])

    def test_no_request_returns_empty_list(self):
        self._set_amounts("10,25")
        value = self.block.to_python({})
        ctx = self.block.get_context(value, parent_context=None)
        self.assertEqual(ctx["donation_suggested_amounts_list"], [])


class TestNavigationSettingsResolvedForPage(TestCase):
    """
    Page tree used by these tests:

        home
        ├── canada
        │   └── canada_program (grandchild — should still inherit canada's nav)
        └── other

    A "canada" override is registered with root_page=canada. Only "canada"
    and pages beneath it should resolve to the override; "home" and "other"
    should fall back to the site default.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = Page(title="Home", slug="nav-override-home")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="nav-override-test.localhost",
            port=80,
            root_page=cls.home,
            site_name="Nav Override Test",
        )
        cls.canada = Page(title="Canada", slug="canada")
        cls.home.add_child(instance=cls.canada)
        cls.canada_program = Page(title="Canada Program", slug="program")
        cls.canada.add_child(instance=cls.canada_program)
        cls.other = Page(title="Other", slug="other")
        cls.home.add_child(instance=cls.other)

        cls.nav, _ = NavigationSettings.objects.get_or_create(site=cls.site)
        cls.nav.navigation_overrides = [
            (
                "override",
                {
                    "root_page": cls.canada,
                    "primary_navigation": [],
                    "cta_text": "",
                    "cta_page": None,
                    "cta_url": "",
                    "cta_anchor": "",
                    "collapse_desktop_menu": False,
                },
            )
        ]
        cls.nav.save()

    def test_root_page_itself_uses_override(self):
        resolved = self.nav.resolved_for_page(self.canada)
        self.assertEqual(resolved.get("root_page").pk, self.canada.pk)

    def test_descendant_of_root_page_uses_override(self):
        resolved = self.nav.resolved_for_page(self.canada_program)
        self.assertEqual(resolved.get("root_page").pk, self.canada.pk)

    def test_unrelated_page_uses_site_default(self):
        resolved = self.nav.resolved_for_page(self.other)
        self.assertIs(resolved, self.nav)

    def test_home_page_uses_site_default(self):
        resolved = self.nav.resolved_for_page(self.home)
        self.assertIs(resolved, self.nav)

    def test_no_page_uses_site_default(self):
        self.assertIs(self.nav.resolved_for_page(None), self.nav)

    def test_no_overrides_uses_site_default(self):
        self.nav.navigation_overrides = []
        self.nav.save()
        self.assertIs(self.nav.resolved_for_page(self.canada), self.nav)

    def test_most_specific_override_wins(self):
        """A nested override (deeper root_page) beats a broader ancestor override."""
        self.nav.navigation_overrides = [
            (
                "override",
                {
                    "root_page": self.canada,
                    "primary_navigation": [],
                    "cta_text": "",
                    "cta_page": None,
                    "cta_url": "",
                    "cta_anchor": "",
                    "collapse_desktop_menu": False,
                },
            ),
            (
                "override",
                {
                    "root_page": self.canada_program,
                    "primary_navigation": [],
                    "cta_text": "",
                    "cta_page": None,
                    "cta_url": "",
                    "cta_anchor": "",
                    "collapse_desktop_menu": False,
                },
            ),
        ]
        self.nav.save()
        resolved = self.nav.resolved_for_page(self.canada_program)
        self.assertEqual(resolved.get("root_page").pk, self.canada_program.pk)


class TestNavigationOverrideRendersInHeader(TestCase):
    """
    End-to-end check that {% resolved_navigation %} (wtrx_tags.py), wired up
    in wtrx/templates/wtrx/navigation/header.html, actually renders the
    override's links for pages under its root_page and the default site
    links everywhere else — not just that resolved_for_page() picks the
    right value in isolation.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="header-render-home")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="header-render-test.localhost",
            port=80,
            root_page=cls.home,
            site_name="Header Render Test",
        )
        cls.canada = ContentPage(title="Canada", slug="canada")
        cls.home.add_child(instance=cls.canada)
        cls.other = ContentPage(title="Other", slug="other")
        cls.home.add_child(instance=cls.other)

        cls.nav, _ = NavigationSettings.objects.get_or_create(site=cls.site)
        cls.nav.primary_navigation = [
            ("internal", {"text": "Default Link", "page": cls.home})
        ]
        cls.nav.navigation_overrides = [
            (
                "override",
                {
                    "root_page": cls.canada,
                    "primary_navigation": [
                        ("internal", {"text": "Canada Only Link", "page": cls.canada})
                    ],
                    "cta_text": "",
                    "cta_page": None,
                    "cta_url": "",
                    "cta_anchor": "",
                    "collapse_desktop_menu": False,
                },
            )
        ]
        cls.nav.save()

    def setUp(self):
        self.client = Client(HTTP_HOST="header-render-test.localhost")

    def test_default_page_shows_default_nav_only(self):
        response = self.client.get(self.other.url)
        content = response.content.decode()
        self.assertIn("Default Link", content)
        self.assertNotIn("Canada Only Link", content)

    def test_override_root_page_shows_override_nav_only(self):
        response = self.client.get(self.canada.url)
        content = response.content.decode()
        self.assertIn("Canada Only Link", content)
        self.assertNotIn("Default Link", content)


class TestRegionalLabelRendersInHeader(TestCase):
    """
    The regional badge beside the logo (Figma "Regional Nav"). The label comes
    from the resolved navigation, so it is inherited by every page beneath an
    override's root page, and the whole logo lockup links to that root page
    rather than the site root.

    Tree:
        home
        ├── canada          (override root_page, regional_label="Canada")
        │   └── program     (descendant — should inherit the badge)
        └── other           (outside the override — no badge)
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="regional-label-home")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="regional-label-test.localhost",
            port=80,
            root_page=cls.home,
            site_name="Regional Label Test",
        )
        cls.canada = ContentPage(title="Canada", slug="canada")
        cls.home.add_child(instance=cls.canada)
        cls.program = ContentPage(title="Program", slug="program")
        cls.canada.add_child(instance=cls.program)
        cls.other = ContentPage(title="Other", slug="other")
        cls.home.add_child(instance=cls.other)

        cls.nav, _ = NavigationSettings.objects.get_or_create(site=cls.site)
        cls.nav.navigation_overrides = [
            (
                "override",
                {
                    "root_page": cls.canada,
                    "regional_label": "Canada",
                    "primary_navigation": [],
                    "cta_text": "",
                    "cta_page": None,
                    "cta_url": "",
                    "cta_anchor": "",
                    "collapse_desktop_menu": False,
                },
            )
        ]
        cls.nav.save()

    def setUp(self):
        self.client = Client(HTTP_HOST="regional-label-test.localhost")

    def test_resolved_navigation_exposes_override_label(self):
        resolved = self.nav.resolved_for_page(self.canada)
        self.assertEqual(resolved.get("regional_label"), "Canada")

    def test_site_default_exposes_blank_label_and_no_root_page(self):
        """
        resolved_for_page() promises the same attribute names either way, so
        the site default must answer to both reads the header makes.
        """
        resolved = self.nav.resolved_for_page(self.other)
        self.assertIs(resolved, self.nav)
        self.assertEqual(resolved.regional_label, "")
        self.assertIsNone(resolved.root_page)

    def test_badge_renders_on_override_root_page(self):
        content = self.client.get(self.canada.url).content.decode()
        self.assertIn("wtr-regional-label", content)
        self.assertIn("Canada", content)

    def test_badge_renders_on_descendant_page(self):
        content = self.client.get(self.program.url).content.decode()
        self.assertIn("wtr-regional-label", content)

    def test_no_badge_outside_the_override(self):
        content = self.client.get(self.other.url).content.decode()
        self.assertNotIn("wtr-regional-label", content)

    def test_no_badge_when_label_is_blank(self):
        self.nav.navigation_overrides = [
            (
                "override",
                {
                    "root_page": self.canada,
                    "regional_label": "",
                    "primary_navigation": [],
                    "cta_text": "",
                    "cta_page": None,
                    "cta_url": "",
                    "cta_anchor": "",
                    "collapse_desktop_menu": False,
                },
            )
        ]
        self.nav.save()
        content = self.client.get(self.canada.url).content.decode()
        self.assertNotIn("wtr-regional-label", content)

    def test_lockup_links_to_override_root_page(self):
        content = self.client.get(self.program.url).content.decode()
        # {% pageurl %} emits a relative path; page.url is absolute here because
        # this test's Site is not the default site.
        self.assertIn('<a href="/canada/" class="group flex items-center gap-4', content)

    def test_lockup_links_to_site_root_without_an_override(self):
        content = self.client.get(self.other.url).content.decode()
        self.assertIn('<a href="/" class="group flex items-center gap-4', content)

    def test_site_wide_label_renders_without_any_override(self):
        """A standalone regional fork sets the label once on NavigationSettings."""
        self.nav.navigation_overrides = []
        self.nav.regional_label = "Indonesia"
        self.nav.save()
        content = self.client.get(self.other.url).content.decode()
        self.assertIn("wtr-regional-label", content)
        self.assertIn("Indonesia", content)


class TestHeaderLogoRendering(TestCase):
    """
    The header logo hovers with the regional badge beside it, both driven by
    "group" on the lockup anchor.

    It is a CSS filter rather than a recolour because an <img> is opaque to
    colour properties — no fill or currentColor reaches inside it, whether it
    holds an SVG or a PNG. brightness(0.55) takes 350's #0F81E9 to #084780,
    6/255 off --color-navy. The point of these tests is that the treatment is
    format-independent: SVG and raster logos get the identical markup, so a
    fork uploading a PNG (or a multi-colour SVG) still gets a working hover
    instead of a silently missing or broken one.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="logo-render-home")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="logo-render-test.localhost",
            port=80,
            root_page=cls.home,
            site_name="Logo Render Test",
        )
        cls.branding = BrandingSEOSettings.objects.create(site=cls.site)

    def setUp(self):
        self.client = Client(HTTP_HOST="logo-render-test.localhost")

    def _set_logo(self, filename, content, content_type):
        image = CustomImage.objects.create(
            title="Logo",
            file=SimpleUploadedFile(filename, content, content_type=content_type),
            width=95,
            height=41,
        )
        self.branding.logo = image
        self.branding.save()
        return image

    def _header(self):
        html = self.client.get(self.home.url).content.decode()
        return html[html.find("<header") : html.find("</header>")]

    def test_svg_logo_hovers_toward_navy(self):
        self._set_logo("logo.svg", SVG_LOGO, "image/svg+xml")
        self.assertIn("group-hover:brightness-[0.55]", self._header())

    def test_raster_logo_gets_the_same_hover(self):
        """The whole reason for a filter over a mask or an inline SVG."""
        self._set_logo("logo.png", PNG_PIXEL, "image/png")
        self.assertIn("group-hover:brightness-[0.55]", self._header())

    def test_logo_is_a_plain_img_whatever_the_format(self):
        for filename, content, content_type in (
            ("logo.svg", SVG_LOGO, "image/svg+xml"),
            ("logo.png", PNG_PIXEL, "image/png"),
        ):
            with self.subTest(filename=filename):
                self._set_logo(filename, content, content_type)
                header = self._header()
                self.assertIn("<img", header)
                self.assertIn('alt="Logo Render Test"', header)
                self.assertIn("wtr-logo", header)

    def test_hover_transition_is_present(self):
        """Without `transition` the filter snaps instead of easing."""
        self._set_logo("logo.svg", SVG_LOGO, "image/svg+xml")
        self.assertIn("transition group-hover:brightness", self._header())

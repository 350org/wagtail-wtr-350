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
- TestIsIntegrationEnabled: IntegrationSettings.is_integration_enabled()'s
  default_enabled fallback — the mechanism that lets a built-in,
  non-third-party block variant (Wagtail Forms) stay visible with zero
  configuration while every genuine third-party integration stays hidden
  until explicitly configured.
"""

import base64
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, SimpleTestCase, TestCase
from wagtail.models import Page, Site

from wtrx.blocks import DonateBlock
from wtrx.images import CustomImage
from wtrx.integrations.actionkit import ActionKitError
from wtrx.models import ContentPage, HomePage
from wtrx.site_settings import (
    BrandingSEOSettings,
    FooterSettings,
    IntegrationSettings,
    NavigationSettings,
    SocialSettings,
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


class TestIsIntegrationEnabled(TestCase):
    """
    IntegrationSettings.is_integration_enabled() drives block visibility in
    the editor (wagtail_hooks.py). Its default_enabled fallback is what makes
    a built-in feature (Wagtail Forms) independently hideable per site
    without being hidden by default the way a real third-party integration is.
    """

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.get(is_default_site=True)
        cls.integration, _ = IntegrationSettings.objects.get_or_create(
            site=cls.site,
        )

    def _set_integrations(self, data):
        self.integration.integrations = data
        self.integration.save()

    def test_no_entry_and_default_enabled_false_is_disabled(self):
        """A genuine third-party integration with no entry reads as disabled."""
        self._set_integrations([])
        self.assertFalse(self.integration.is_integration_enabled("actblue"))
        self.assertFalse(self.integration.is_integration_enabled("actionkit"))
        self.assertFalse(self.integration.is_integration_enabled("fundraiseup"))
        self.assertFalse(self.integration.is_integration_enabled("action_network"))

    def test_no_entry_and_default_enabled_true_is_enabled(self):
        """Wagtail Forms reads as enabled with no entry at all — it's built-in."""
        self._set_integrations([])
        self.assertTrue(self.integration.is_integration_enabled("wagtail_forms"))

    def test_explicit_disabled_entry_overrides_default_enabled_true(self):
        self._set_integrations([("wagtail_forms", {"enabled": False})])
        self.assertFalse(self.integration.is_integration_enabled("wagtail_forms"))

    def test_explicit_enabled_entry_overrides_default_enabled_false(self):
        self._set_integrations(
            [
                (
                    "actblue",
                    {
                        "enabled": True,
                        "base_url": "",
                        "suggested_amounts": "",
                        "default_recurring": False,
                    },
                )
            ]
        )
        self.assertTrue(self.integration.is_integration_enabled("actblue"))

    def test_unknown_slug_is_disabled(self):
        """A slug with no registered IntegrationType at all is never enabled."""
        self._set_integrations([])
        self.assertFalse(self.integration.is_integration_enabled("not-a-real-slug"))

    def test_enabled_slugs_by_category_includes_default_enabled_with_no_entry(self):
        """wagtail_forms shows up in the 'signup' category with no entry needed."""
        self._set_integrations([])
        self.assertIn(
            "wagtail_forms", self.integration.enabled_slugs_by_category("signup")
        )

    def test_enabled_slugs_by_category_excludes_explicitly_disabled(self):
        self._set_integrations([("wagtail_forms", {"enabled": False})])
        self.assertNotIn(
            "wagtail_forms", self.integration.enabled_slugs_by_category("signup")
        )

    def test_enabling_actionkit_hides_wagtail_forms_by_default(self):
        """
        A default_enabled=True slug with no entry of its own yields to a
        sibling in the same category that's been explicitly enabled — a
        site that's wired up a real signup integration shouldn't also see
        the built-in form option in the picker with zero effort.
        """
        self._set_integrations(
            [
                (
                    "actionkit",
                    {
                        "enabled": True,
                        "hostname": "x.actionkit.com",
                        "api_username": "u",
                        "api_password": "",
                    },
                )
            ]
        )
        self.assertFalse(self.integration.is_integration_enabled("wagtail_forms"))

    def test_enabling_action_network_hides_wagtail_forms_by_default(self):
        self._set_integrations([("action_network", {"enabled": True, "api_key": ""})])
        self.assertFalse(self.integration.is_integration_enabled("wagtail_forms"))

    def test_explicit_wagtail_forms_entry_overrides_category_yielding(self):
        """An explicit entry for Wagtail Forms itself always wins, even with
        a sibling signup integration enabled."""
        self._set_integrations(
            [
                (
                    "actionkit",
                    {
                        "enabled": True,
                        "hostname": "x.actionkit.com",
                        "api_username": "u",
                        "api_password": "",
                    },
                ),
                ("wagtail_forms", {"enabled": True}),
            ]
        )
        self.assertTrue(self.integration.is_integration_enabled("wagtail_forms"))

    def test_enabling_a_donation_integration_does_not_hide_wagtail_forms(self):
        """Category-yielding is scoped to the same category — a donation
        integration is unrelated to the signup category Wagtail Forms is in."""
        self._set_integrations(
            [
                (
                    "actblue",
                    {
                        "enabled": True,
                        "base_url": "",
                        "suggested_amounts": "",
                        "default_recurring": False,
                    },
                )
            ]
        )
        self.assertTrue(self.integration.is_integration_enabled("wagtail_forms"))

    def test_disabled_sibling_entry_does_not_hide_wagtail_forms(self):
        """An entry that exists but is itself disabled doesn't count as
        "explicitly enabled" for the purposes of yielding."""
        self._set_integrations(
            [
                (
                    "actionkit",
                    {
                        "enabled": False,
                        "hostname": "x.actionkit.com",
                        "api_username": "u",
                        "api_password": "",
                    },
                )
            ]
        )
        self.assertTrue(self.integration.is_integration_enabled("wagtail_forms"))


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


class TestFooterSettingsResolvedForPage(TestCase):
    """
    FooterSettings.resolved_for_page() — identical algorithm to
    NavigationSettings.resolved_for_page(), see
    TestNavigationSettingsResolvedForPage for the page tree this mirrors.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = Page(title="Home", slug="footer-override-home")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="footer-override-test.localhost",
            port=80,
            root_page=cls.home,
            site_name="Footer Override Test",
        )
        cls.canada = Page(title="Canada", slug="canada")
        cls.home.add_child(instance=cls.canada)
        cls.canada_program = Page(title="Canada Program", slug="program")
        cls.canada.add_child(instance=cls.canada_program)
        cls.other = Page(title="Other", slug="other")
        cls.home.add_child(instance=cls.other)

        cls.footer, _ = FooterSettings.objects.get_or_create(site=cls.site)
        cls.footer.footer_overrides = [
            (
                "override",
                {
                    "root_page": cls.canada,
                    "regional_label": "",
                    "layout": "",
                    "footer_navigation": [],
                    "minimal_links": [],
                    "copyright_text": "",
                },
            )
        ]
        cls.footer.save()

    def test_root_page_itself_uses_override(self):
        resolved = self.footer.resolved_for_page(self.canada)
        self.assertEqual(resolved.get("root_page").pk, self.canada.pk)

    def test_descendant_of_root_page_uses_override(self):
        resolved = self.footer.resolved_for_page(self.canada_program)
        self.assertEqual(resolved.get("root_page").pk, self.canada.pk)

    def test_unrelated_page_uses_site_default(self):
        resolved = self.footer.resolved_for_page(self.other)
        self.assertIs(resolved, self.footer)

    def test_home_page_uses_site_default(self):
        resolved = self.footer.resolved_for_page(self.home)
        self.assertIs(resolved, self.footer)

    def test_no_page_uses_site_default(self):
        self.assertIs(self.footer.resolved_for_page(None), self.footer)

    def test_no_overrides_uses_site_default(self):
        self.footer.footer_overrides = []
        self.footer.save()
        self.assertIs(self.footer.resolved_for_page(self.canada), self.footer)

    def test_most_specific_override_wins(self):
        """A nested override (deeper root_page) beats a broader ancestor override."""
        self.footer.footer_overrides = [
            (
                "override",
                {
                    "root_page": self.canada,
                    "regional_label": "",
                    "layout": "",
                    "footer_navigation": [],
                    "minimal_links": [],
                    "copyright_text": "",
                },
            ),
            (
                "override",
                {
                    "root_page": self.canada_program,
                    "regional_label": "",
                    "layout": "",
                    "footer_navigation": [],
                    "minimal_links": [],
                    "copyright_text": "",
                },
            ),
        ]
        self.footer.save()
        resolved = self.footer.resolved_for_page(self.canada_program)
        self.assertEqual(resolved.get("root_page").pk, self.canada_program.pk)


class TestFooterOverrideRendersInFooter(TestCase):
    """
    End-to-end check that {% resolved_footer %} (wtrx_tags.py), wired up in
    wtrx/templates/wtrx/navigation/footer.html, actually renders the
    override's columns for pages under its root_page and the default site
    columns everywhere else.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="footer-render-home")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="footer-render-test.localhost",
            port=80,
            root_page=cls.home,
            site_name="Footer Render Test",
        )
        cls.canada = ContentPage(title="Canada", slug="canada")
        cls.home.add_child(instance=cls.canada)
        cls.other = ContentPage(title="Other", slug="other")
        cls.home.add_child(instance=cls.other)

        cls.footer, _ = FooterSettings.objects.get_or_create(site=cls.site)
        cls.footer.footer_navigation = [
            (
                "column",
                {
                    "heading": "Default Column",
                    "links": [("internal", {"text": "Default Link", "page": cls.home})],
                },
            )
        ]
        cls.footer.footer_overrides = [
            (
                "override",
                {
                    "root_page": cls.canada,
                    "regional_label": "",
                    "layout": "",
                    "footer_navigation": [
                        (
                            "column",
                            {
                                "heading": "Canada Column",
                                "links": [
                                    (
                                        "internal",
                                        {"text": "Canada Only Link", "page": cls.canada},
                                    )
                                ],
                            },
                        )
                    ],
                    "minimal_links": [],
                    "copyright_text": "",
                },
            )
        ]
        cls.footer.save()

    def setUp(self):
        self.client = Client(HTTP_HOST="footer-render-test.localhost")

    def test_default_page_shows_default_footer_only(self):
        response = self.client.get(self.other.url)
        content = response.content.decode()
        self.assertIn("Default Link", content)
        self.assertNotIn("Canada Only Link", content)

    def test_override_root_page_shows_override_footer_only(self):
        response = self.client.get(self.canada.url)
        content = response.content.decode()
        self.assertIn("Canada Only Link", content)
        self.assertNotIn("Default Link", content)


class TestFooterRegionalLabelRendersInFooter(TestCase):
    """
    The footer's regional badge, driven by regional_label on a footer
    override — independent of NavigationSettings.regional_label by design
    (FooterSettings is self-contained, same as every other settings model).

    Tree:
        home
        ├── canada          (override root_page, regional_label="Canada")
        │   └── program     (descendant — should inherit the badge)
        └── other           (outside the override — no badge)
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="footer-regional-label-home")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="footer-regional-label-test.localhost",
            port=80,
            root_page=cls.home,
            site_name="Footer Regional Label Test",
        )
        cls.canada = ContentPage(title="Canada", slug="canada")
        cls.home.add_child(instance=cls.canada)
        cls.program = ContentPage(title="Program", slug="program")
        cls.canada.add_child(instance=cls.program)
        cls.other = ContentPage(title="Other", slug="other")
        cls.home.add_child(instance=cls.other)

        cls.footer, _ = FooterSettings.objects.get_or_create(site=cls.site)
        cls.footer.footer_overrides = [
            (
                "override",
                {
                    "root_page": cls.canada,
                    "regional_label": "Canada",
                    "layout": "",
                    "footer_navigation": [],
                    "minimal_links": [],
                    "copyright_text": "",
                },
            )
        ]
        cls.footer.save()

    def setUp(self):
        self.client = Client(HTTP_HOST="footer-regional-label-test.localhost")

    def test_resolved_footer_exposes_override_label(self):
        resolved = self.footer.resolved_for_page(self.canada)
        self.assertEqual(resolved.get("regional_label"), "Canada")

    def test_site_default_exposes_blank_label_and_no_root_page(self):
        resolved = self.footer.resolved_for_page(self.other)
        self.assertIs(resolved, self.footer)
        self.assertEqual(resolved.regional_label, "")
        self.assertIsNone(resolved.root_page)

    def test_badge_renders_on_override_root_page(self):
        content = self.client.get(self.canada.url).content.decode()
        self.assertIn("wtr-footer-regional-label", content)
        self.assertIn("Canada", content)

    def test_badge_renders_on_descendant_page(self):
        content = self.client.get(self.program.url).content.decode()
        self.assertIn("wtr-footer-regional-label", content)

    def test_no_badge_outside_the_override(self):
        content = self.client.get(self.other.url).content.decode()
        self.assertNotIn("wtr-footer-regional-label", content)

    def test_no_badge_when_label_is_blank(self):
        self.footer.footer_overrides = [
            (
                "override",
                {
                    "root_page": self.canada,
                    "regional_label": "",
                    "layout": "",
                    "footer_navigation": [],
                    "minimal_links": [],
                    "copyright_text": "",
                },
            )
        ]
        self.footer.save()
        content = self.client.get(self.canada.url).content.decode()
        self.assertNotIn("wtr-footer-regional-label", content)

    def test_lockup_links_to_override_root_page(self):
        content = self.client.get(self.program.url).content.decode()
        self.assertIn(
            '<a href="/canada/" class="inline-flex items-center gap-2">', content
        )

    def test_lockup_links_to_site_root_without_an_override(self):
        content = self.client.get(self.other.url).content.decode()
        self.assertIn('<a href="/" class="inline-flex items-center gap-2">', content)


class TestRegionalSitesSwitcherRendersInFooter(TestCase):
    """
    The "Around the World" region switcher (FooterSettings.regional_sites) —
    a flat, site-wide list of links to other regional 350.org sites, shown
    beside the footer logo. Unlike footer_overrides, this list is not
    region-scoped content itself, so it must render identically on every
    page regardless of any footer override in effect.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="regional-sites-home")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="regional-sites-test.localhost",
            port=80,
            root_page=cls.home,
            site_name="Regional Sites Test",
        )
        cls.canada = ContentPage(title="Canada", slug="canada")
        cls.home.add_child(instance=cls.canada)

        cls.footer, _ = FooterSettings.objects.get_or_create(site=cls.site)
        cls.footer.regional_sites = [
            ("site", {"text": "Canada", "url": "https://canada.350.org"}),
            ("site", {"text": "Indonesia", "url": "https://350.or.id"}),
        ]
        cls.footer.footer_overrides = [
            (
                "override",
                {
                    "root_page": cls.canada,
                    "regional_label": "Canada",
                    "layout": "",
                    "footer_navigation": [],
                    "minimal_links": [],
                    "copyright_text": "",
                },
            )
        ]
        cls.footer.save()

    def setUp(self):
        self.client = Client(HTTP_HOST="regional-sites-test.localhost")

    def test_switcher_renders_on_default_page(self):
        content = self.client.get(self.home.url).content.decode()
        self.assertIn("wtr-regional-sites", content)
        self.assertIn("https://canada.350.org", content)
        self.assertIn("https://350.or.id", content)

    def test_switcher_also_renders_on_page_under_an_override(self):
        """Not scoped by footer_overrides — same list everywhere."""
        content = self.client.get(self.canada.url).content.decode()
        self.assertIn("wtr-regional-sites", content)
        self.assertIn("https://canada.350.org", content)

    def test_no_switcher_when_regional_sites_is_empty(self):
        self.footer.regional_sites = []
        self.footer.save()
        content = self.client.get(self.home.url).content.decode()
        self.assertNotIn("wtr-regional-sites", content)


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


class TestFooterNewsletterSignupRendersInFooter(TestCase):
    """
    The footer's newsletter signup box — {% resolved_footer_newsletter_signup %}
    (wtrx_tags.py), reusing SignupActionKitBlock's own fetched-form renderer
    (_actionkit_form.html) rather than hand-building email/country fields.

    Tree:
        home
        └── canada  (footer override, its own newsletter_actionkit_shortname)

    FooterSettings.newsletter_actionkit_shortname is the site default; the
    canada override sets a different shortname, so the two pages must fetch
    (and cache) two distinct ActionKit forms.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="newsletter-home")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="newsletter-test.localhost",
            port=80,
            root_page=cls.home,
            site_name="Newsletter Test",
        )
        cls.canada = ContentPage(title="Canada", slug="canada")
        cls.home.add_child(instance=cls.canada)

        IntegrationSettings.objects.update_or_create(
            site=cls.site,
            defaults={
                "integrations": [
                    (
                        "actionkit",
                        {
                            "enabled": True,
                            "hostname": "myorg.actionkit.com",
                            "api_username": "",
                            "api_password": "",
                        },
                    )
                ],
            },
        )

        cls.footer, _ = FooterSettings.objects.get_or_create(site=cls.site)
        cls.footer.newsletter_actionkit_shortname = "newsletter"
        cls.footer.footer_overrides = [
            (
                "override",
                {
                    "root_page": cls.canada,
                    "regional_label": "",
                    "layout": "",
                    "footer_navigation": [],
                    "minimal_links": [],
                    "copyright_text": "",
                    "newsletter_actionkit_shortname": "newsletter-canada",
                },
            )
        ]
        cls.footer.save()

    def setUp(self):
        cache.clear()
        self.client = Client(HTTP_HOST="newsletter-test.localhost")

    @patch("wtrx.integrations.actionkit.fetch_embed_form_html")
    def test_default_page_fetches_and_renders_the_site_default_shortname(self, mock_fetch):
        mock_fetch.return_value = "<form>default form</form>"
        content = self.client.get(self.home.url).content.decode()
        self.assertIn("default form", content)
        mock_fetch.assert_called_once_with("myorg.actionkit.com", "newsletter")

    @patch("wtrx.integrations.actionkit.fetch_embed_form_html")
    def test_override_page_fetches_and_renders_the_override_shortname(self, mock_fetch):
        mock_fetch.return_value = "<form>canada form</form>"
        content = self.client.get(self.canada.url).content.decode()
        self.assertIn("canada form", content)
        mock_fetch.assert_called_once_with("myorg.actionkit.com", "newsletter-canada")

    @patch("wtrx.integrations.actionkit.fetch_embed_form_html")
    def test_second_render_within_cache_window_does_not_refetch(self, mock_fetch):
        mock_fetch.return_value = "<form>default form</form>"
        self.client.get(self.home.url)
        self.client.get(self.home.url)
        mock_fetch.assert_called_once()

    def test_no_signup_box_when_shortname_is_blank(self):
        self.footer.newsletter_actionkit_shortname = ""
        self.footer.footer_overrides = []
        self.footer.save()
        content = self.client.get(self.home.url).content.decode()
        self.assertNotIn("wtr-footer-newsletter", content)

    @patch("wtrx.integrations.actionkit.fetch_embed_form_html")
    def test_fetch_failure_shows_unavailable_fallback(self, mock_fetch):
        mock_fetch.side_effect = ActionKitError("boom")
        content = self.client.get(self.home.url).content.decode()
        self.assertIn("wtr-footer-newsletter", content)
        self.assertIn("temporarily unavailable", content)

    def test_box_shows_unavailable_fallback_when_actionkit_not_configured(self):
        """A shortname is set but ActionKit itself isn't — box still renders, form falls back."""
        integration = IntegrationSettings.for_site(self.site)
        integration.integrations = []
        integration.save()
        content = self.client.get(self.home.url).content.decode()
        self.assertIn("wtr-footer-newsletter", content)
        self.assertIn("temporarily unavailable", content)

    @patch("wtrx.integrations.actionkit.fetch_embed_form_html")
    def test_wrapper_carries_the_shared_actionkit_scoping_class(self, mock_fetch):
        """
        _actionkit_form.html's script scopes itself to the nearest
        .wtr-signup-actionkit ancestor (document.currentScript.closest(...))
        so this box's form is found independently of any other ActionKit
        embed already on the page — see the class comment in footer.html.
        """
        mock_fetch.return_value = "<form>default form</form>"
        content = self.client.get(self.home.url).content.decode()
        self.assertIn('wtr-footer-newsletter wtr-signup-actionkit"', content)

    @patch("wtrx.integrations.actionkit.fetch_embed_form_html")
    def test_default_page_renders_site_default_success_message(self, mock_fetch):
        mock_fetch.return_value = "<form>default form</form>"
        content = self.client.get(self.home.url).content.decode()
        self.assertIn("Thanks for signing up!", content)
        self.assertIn("data-thank-you", content)

    @patch("wtrx.integrations.actionkit.fetch_embed_form_html")
    def test_override_success_message_overrides_site_default(self, mock_fetch):
        mock_fetch.return_value = "<form>canada form</form>"
        overrides = self.footer.footer_overrides
        overrides[0].value["newsletter_success_message"] = "Merci de vous inscrire!"
        self.footer.footer_overrides = overrides
        self.footer.save()
        content = self.client.get(self.canada.url).content.decode()
        self.assertIn("Merci de vous inscrire!", content)
        self.assertNotIn("Thanks for signing up!", content)

    @patch("wtrx.integrations.actionkit.fetch_embed_form_html")
    def test_override_falls_back_to_site_default_success_message_when_blank(self, mock_fetch):
        """
        Unlike every other field on FooterOverrideBlock, a blank
        newsletter_success_message falls back to the site default rather
        than resolving to nothing — see resolved_footer_newsletter_signup()'s
        docstring. Leaving it unset on an override must not silently disable
        the inline AJAX submit path for that section.
        """
        mock_fetch.return_value = "<form>canada form</form>"
        content = self.client.get(self.canada.url).content.decode()
        self.assertIn("Thanks for signing up!", content)


class TestSocialSettingsTwitterHandle(TestCase):
    """
    SocialSettings.twitter_handle derives the twitter:site meta tag's
    "@handle" from social_links's own "twitter" entry -- replaces the old
    separate BrandingSEOSettings.twitter_site field (see the migration
    that removed it, 0068/0069), which could disagree with social_links.
    """

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.get(is_default_site=True)
        cls.social, _ = SocialSettings.objects.get_or_create(site=cls.site)

    def _set_links(self, links):
        self.social.social_links = links
        self.social.save()

    def test_empty_when_no_social_links(self):
        self._set_links([])
        self.assertEqual(self.social.twitter_handle, "")

    def test_empty_when_no_twitter_entry(self):
        self._set_links(
            [("link", {"platform": "facebook", "url": "https://facebook.com/350"})]
        )
        self.assertEqual(self.social.twitter_handle, "")

    def test_handle_derived_from_twitter_com_url(self):
        self._set_links([("link", {"platform": "twitter", "url": "https://twitter.com/350"})])
        self.assertEqual(self.social.twitter_handle, "@350")

    def test_handle_derived_from_x_com_url(self):
        self._set_links([("link", {"platform": "twitter", "url": "https://x.com/350"})])
        self.assertEqual(self.social.twitter_handle, "@350")

    def test_handle_strips_trailing_slash_and_extra_path(self):
        self._set_links(
            [("link", {"platform": "twitter", "url": "https://twitter.com/350/status/1"})]
        )
        self.assertEqual(self.social.twitter_handle, "@350")

    def test_empty_when_twitter_url_has_no_path(self):
        self._set_links([("link", {"platform": "twitter", "url": "https://twitter.com/"})])
        self.assertEqual(self.social.twitter_handle, "")


class TestIntegrationSettingsHeadHtml(TestCase):
    """
    IntegrationSettings.head_html() concatenates every enabled
    integration's head_html_field, followed by custom_head_html.
    GoogleTagManagerConfigBlock (wtrx/integrations/gtm.py) is the first
    real integration to exercise head_html_field end to end -- Fundraise
    Up's own installation_code covers this too, but GTM is used here
    since it's this suite's own natural fixture for both head and body.
    """

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.get(is_default_site=True)
        cls.integration, _ = IntegrationSettings.objects.get_or_create(site=cls.site)

    def _gtm_entry(self, enabled=True, head_snippet="<script>gtm head</script>", body_snippet=""):
        return (
            "google_tag_manager",
            {
                "enabled": enabled,
                "head_snippet": head_snippet,
                "body_snippet": body_snippet,
            },
        )

    def test_empty_when_nothing_configured(self):
        self.assertEqual(str(self.integration.head_html()), "")

    def test_renders_head_snippet_for_an_enabled_gtm_entry(self):
        self.integration.integrations = [self._gtm_entry()]
        self.assertIn("<script>gtm head</script>", str(self.integration.head_html()))

    def test_omits_head_snippet_for_a_disabled_gtm_entry(self):
        self.integration.integrations = [self._gtm_entry(enabled=False)]
        self.assertEqual(str(self.integration.head_html()), "")

    def test_appends_custom_head_html_after_integration_fragments(self):
        self.integration.integrations = [self._gtm_entry()]
        self.integration.custom_head_html = "<meta name=\"custom\">"
        html = str(self.integration.head_html())
        self.assertIn("<script>gtm head</script>", html)
        self.assertIn('<meta name="custom">', html)
        self.assertLess(
            html.index("gtm head"), html.index("custom"),
            "custom_head_html should come after integration fragments",
        )

    def test_custom_head_html_alone_with_no_integrations_configured(self):
        self.integration.custom_head_html = "<meta name=\"custom\">"
        self.assertIn('<meta name="custom">', str(self.integration.head_html()))


class TestIntegrationSettingsBodyHtml(TestCase):
    """
    IntegrationSettings.body_html() mirrors head_html() but reads
    IntegrationType.body_html_field/custom_body_html instead -- see
    registry.py. GoogleTagManagerConfigBlock (wtrx/integrations/gtm.py) is
    the first real integration to set body_html_field (its <noscript>
    fallback).
    """

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.get(is_default_site=True)
        cls.integration, _ = IntegrationSettings.objects.get_or_create(site=cls.site)

    def _gtm_entry(self, enabled=True, head_snippet="<script>gtm head</script>", body_snippet="<noscript>gtm body</noscript>"):
        return (
            "google_tag_manager",
            {
                "enabled": enabled,
                "head_snippet": head_snippet,
                "body_snippet": body_snippet,
            },
        )

    def test_empty_when_nothing_configured(self):
        self.assertEqual(str(self.integration.body_html()), "")

    def test_renders_body_snippet_for_an_enabled_gtm_entry(self):
        self.integration.integrations = [self._gtm_entry()]
        self.assertIn(
            "<noscript>gtm body</noscript>", str(self.integration.body_html())
        )

    def test_body_snippet_stays_optional(self):
        # GTM's own body_snippet field is required=False -- an
        # Analytics-only setup (no Tag Manager) has no <noscript>
        # fallback to paste.
        self.integration.integrations = [self._gtm_entry(body_snippet="")]
        self.assertEqual(str(self.integration.body_html()), "")

    def test_appends_custom_body_html_after_integration_fragments(self):
        self.integration.integrations = [self._gtm_entry()]
        self.integration.custom_body_html = "<div>custom</div>"
        html = str(self.integration.body_html())
        self.assertIn("<noscript>gtm body</noscript>", html)
        self.assertIn("<div>custom</div>", html)
        self.assertLess(
            html.index("gtm body"), html.index("custom"),
            "custom_body_html should come after integration fragments",
        )


class TestIntegrationSettingsCustomHtmlValidation(SimpleTestCase):
    """
    custom_head_html/custom_body_html reuse the same tag-balance validator
    RawHTMLBlock.clean() uses for StreamField content (AGENTS.md pitfall
    #43), via wtrx.validators.validate_balanced_html -- wired up as a
    plain Django model-field validator instead of a block-level clean().
    Uses Field.clean(value, instance) to validate just this one field,
    rather than a full model full_clean() that would also require a real
    `site` FK and every other required field on the model.
    """

    def _clean(self, field_name, value):
        field = IntegrationSettings._meta.get_field(field_name)
        return field.clean(value, IntegrationSettings())

    def test_balanced_html_passes(self):
        self._clean("custom_head_html", "<script>ok();</script>")
        self._clean("custom_body_html", "<div><p>ok</p></div>")

    def test_unbalanced_html_raises(self):
        with self.assertRaises(ValidationError):
            self._clean("custom_head_html", "<div><span></div>")
        with self.assertRaises(ValidationError):
            self._clean("custom_body_html", "<div><span></div>")

    def test_blank_is_allowed(self):
        self._clean("custom_head_html", "")
        self._clean("custom_body_html", "")

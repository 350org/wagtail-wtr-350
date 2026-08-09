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
"""

from django.test import Client, RequestFactory, TestCase
from wagtail.models import Page, Site

from wtrx.blocks import DonateBlock
from wtrx.models import ContentPage, HomePage
from wtrx.site_settings import IntegrationSettings, NavigationSettings


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

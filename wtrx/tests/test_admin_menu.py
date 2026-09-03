"""
Tests for the configurable admin sidebar shortcuts
(AdminMenuSettings.sidebar_shortcuts, added via wagtail_hooks.py's
add_admin_menu_shortcuts() construct_main_menu hook) — a generalization of
what used to be two hardcoded fields/MenuItem subclasses, one each for a
"Blog" and "Press releases" shortcut. See git history for that version.
"""

from django.test import RequestFactory, TestCase
from django.urls import reverse
from wagtail.models import Page, Site

from wtrx.models import Blogs
from wtrx.site_settings import AdminMenuSettings
from wtrx.wagtail_hooks import add_admin_menu_shortcuts


class TestAdminMenuShortcuts(TestCase):
    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = Page(title="Home", slug="admin-menu-home")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="admin-menu-test.localhost",
            port=80,
            root_page=cls.home,
            site_name="Admin Menu Test",
        )
        cls.blog_index = Blogs(title="Blog", slug="blog")
        cls.home.add_child(instance=cls.blog_index)
        cls.press_releases_index = Blogs(title="Press Releases", slug="press-releases")
        cls.home.add_child(instance=cls.press_releases_index)

        cls.admin_settings, _ = AdminMenuSettings.objects.get_or_create(site=cls.site)

    def setUp(self):
        self.factory = RequestFactory()

    def _request(self):
        return self.factory.get("/admin/", HTTP_HOST=self.site.hostname)

    def _set_shortcuts(self, shortcuts):
        self.admin_settings.sidebar_shortcuts = shortcuts
        self.admin_settings.save()

    def test_no_items_added_when_unset(self):
        self._set_shortcuts([])
        items = []
        add_admin_menu_shortcuts(self._request(), items)
        self.assertEqual(items, [])

    def test_item_added_for_a_configured_page(self):
        self._set_shortcuts(
            [("shortcut", {"label": "Blog", "page": self.blog_index, "icon": ""})]
        )
        items = []
        add_admin_menu_shortcuts(self._request(), items)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].label, "Blog")

    def test_label_falls_back_to_page_title_when_blank(self):
        self._set_shortcuts(
            [("shortcut", {"label": "", "page": self.blog_index, "icon": ""})]
        )
        items = []
        add_admin_menu_shortcuts(self._request(), items)
        self.assertEqual(items[0].label, self.blog_index.title)

    def test_icon_falls_back_to_doc_empty_when_blank(self):
        self._set_shortcuts(
            [("shortcut", {"label": "Blog", "page": self.blog_index, "icon": ""})]
        )
        items = []
        add_admin_menu_shortcuts(self._request(), items)
        self.assertEqual(items[0].icon_name, "doc-empty")

    def test_icon_uses_configured_value(self):
        self._set_shortcuts(
            [
                (
                    "shortcut",
                    {
                        "label": "Press releases",
                        "page": self.press_releases_index,
                        "icon": "clipboard-list",
                    },
                )
            ]
        )
        items = []
        add_admin_menu_shortcuts(self._request(), items)
        self.assertEqual(items[0].icon_name, "clipboard-list")

    def test_multiple_shortcuts_all_added_in_order(self):
        self._set_shortcuts(
            [
                ("shortcut", {"label": "Blog", "page": self.blog_index, "icon": ""}),
                (
                    "shortcut",
                    {
                        "label": "Press releases",
                        "page": self.press_releases_index,
                        "icon": "",
                    },
                ),
            ]
        )
        items = []
        add_admin_menu_shortcuts(self._request(), items)
        self.assertEqual([item.label for item in items], ["Blog", "Press releases"])

    def test_unpublished_page_is_skipped(self):
        self.press_releases_index.live = False
        self.press_releases_index.save()
        self._set_shortcuts(
            [
                (
                    "shortcut",
                    {
                        "label": "Press releases",
                        "page": self.press_releases_index,
                        "icon": "",
                    },
                )
            ]
        )
        items = []
        add_admin_menu_shortcuts(self._request(), items)
        self.assertEqual(items, [])
        self.press_releases_index.live = True
        self.press_releases_index.save()

    def test_url_points_to_configured_page(self):
        self._set_shortcuts(
            [
                (
                    "shortcut",
                    {"label": "Blog", "page": self.blog_index, "icon": ""},
                )
            ]
        )
        items = []
        add_admin_menu_shortcuts(self._request(), items)
        expected_url = reverse("wagtailadmin_explore", args=[self.blog_index.id])
        self.assertEqual(items[0].url, expected_url)

    def test_no_site_settings_row_is_a_silent_no_op(self):
        """
        A request for a site with no AdminMenuSettings row at all (or no
        Site match) must never error -- same "degrade gracefully" contract
        as every other settings-driven feature in this app.
        """
        other_site = Site.objects.create(
            hostname="admin-menu-no-settings.localhost",
            port=80,
            root_page=self.home,
            site_name="No Settings",
        )
        AdminMenuSettings.objects.filter(site=other_site).delete()
        request = self.factory.get("/admin/", HTTP_HOST=other_site.hostname)
        items = []
        add_admin_menu_shortcuts(request, items)
        self.assertEqual(items, [])


class TestSettingsMenuGrouping(TestCase):
    """
    group_site_design_settings_menu_items() (wagtail_hooks.py,
    construct_settings_menu hook) folds BrandingSEOSettings/
    NavigationSettings/FooterSettings/SocialSettings into one "Site
    design" SubmenuMenuItem, leaving IntegrationSettings/AdminMenuSettings
    (and anything else) at the top level of the Settings menu.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def _request(self):
        return self.factory.get("/admin/")

    def _setting_menu_item(self, model):
        from wagtail.contrib.settings.registry import SettingMenuItem

        return SettingMenuItem(model, icon="cog")

    def test_site_design_models_grouped_into_one_submenu(self):
        from wagtail.admin.menu import SubmenuMenuItem

        from wtrx.site_settings import (
            BrandingSEOSettings,
            FooterSettings,
            IntegrationSettings,
            NavigationSettings,
            SocialSettings,
        )
        from wtrx.wagtail_hooks import group_site_design_settings_menu_items

        items = [
            self._setting_menu_item(BrandingSEOSettings),
            self._setting_menu_item(NavigationSettings),
            self._setting_menu_item(FooterSettings),
            self._setting_menu_item(SocialSettings),
            self._setting_menu_item(IntegrationSettings),
        ]
        group_site_design_settings_menu_items(self._request(), items)

        submenus = [item for item in items if isinstance(item, SubmenuMenuItem)]
        self.assertEqual(len(submenus), 1)
        self.assertEqual(submenus[0].name, "site-design")

        # The 4 site-design models are gone from the top-level list, and
        # IntegrationSettings is the only thing left there (not grouped).
        non_submenu_items = [
            item for item in items if not isinstance(item, SubmenuMenuItem)
        ]
        self.assertEqual({item.label for item in non_submenu_items}, {"Integrations"})

        submenu_labels = {
            child.label for child in submenus[0].menu.registered_menu_items
        }
        self.assertEqual(
            submenu_labels,
            {"Branding & SEO", "Navigation", "Footer", "Social"},
        )

    def test_integration_settings_not_grouped(self):
        from wagtail.admin.menu import SubmenuMenuItem

        from wtrx.site_settings import BrandingSEOSettings, IntegrationSettings
        from wtrx.wagtail_hooks import group_site_design_settings_menu_items

        branding_item = self._setting_menu_item(BrandingSEOSettings)
        integration_item = self._setting_menu_item(IntegrationSettings)
        items = [branding_item, integration_item]
        group_site_design_settings_menu_items(self._request(), items)

        self.assertIn(integration_item, items)
        submenus = [item for item in items if isinstance(item, SubmenuMenuItem)]
        self.assertEqual(len(submenus), 1)
        self.assertNotIn(
            integration_item, submenus[0].menu.registered_menu_items
        )

    def test_no_op_when_no_site_design_models_present(self):
        from wtrx.site_settings import IntegrationSettings
        from wtrx.wagtail_hooks import group_site_design_settings_menu_items

        integration_item = self._setting_menu_item(IntegrationSettings)
        items = [integration_item]
        group_site_design_settings_menu_items(self._request(), items)
        self.assertEqual(items, [integration_item])

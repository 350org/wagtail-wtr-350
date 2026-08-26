"""
Tests for the "Blog" and "Press releases" admin sidebar shortcuts
(wtrx/wagtail_hooks.py), which link to whichever page is configured on
AdminMenuSettings and hide themselves when unset or unpublished.
"""

from django.test import RequestFactory, TestCase
from wagtail.models import Page, Site

from wtrx.models import Blogs
from wtrx.site_settings import AdminMenuSettings
from wtrx.wagtail_hooks import BlogMenuItem, PressReleasesMenuItem


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
        self.blog_item = BlogMenuItem("Blog", "#", name="blog")
        self.press_releases_item = PressReleasesMenuItem(
            "Press releases", "#", name="press-releases"
        )

    def _request(self):
        return self.factory.get("/admin/", HTTP_HOST=self.site.hostname)

    def test_blog_hidden_when_unset(self):
        self.assertFalse(self.blog_item.is_shown(self._request()))

    def test_press_releases_hidden_when_unset(self):
        self.assertFalse(self.press_releases_item.is_shown(self._request()))

    def test_blog_shown_when_set_and_live(self):
        self.admin_settings.blog_index_page = self.blog_index
        self.admin_settings.save()
        self.assertTrue(self.blog_item.is_shown(self._request()))
        self.admin_settings.blog_index_page = None
        self.admin_settings.save()

    def test_press_releases_shown_when_set_and_live(self):
        self.admin_settings.press_releases_index_page = self.press_releases_index
        self.admin_settings.save()
        self.assertTrue(self.press_releases_item.is_shown(self._request()))
        self.admin_settings.press_releases_index_page = None
        self.admin_settings.save()

    def test_press_releases_hidden_when_unpublished(self):
        self.press_releases_index.live = False
        self.press_releases_index.save()
        self.admin_settings.press_releases_index_page = self.press_releases_index
        self.admin_settings.save()
        self.assertFalse(self.press_releases_item.is_shown(self._request()))
        self.press_releases_index.live = True
        self.press_releases_index.save()
        self.admin_settings.press_releases_index_page = None
        self.admin_settings.save()

    def test_press_releases_url_points_to_configured_page(self):
        from django.urls import reverse

        self.admin_settings.press_releases_index_page = self.press_releases_index
        self.admin_settings.save()
        component = self.press_releases_item.render_component(self._request())
        expected_url = reverse(
            "wagtailadmin_explore", args=[self.press_releases_index.id]
        )
        self.assertEqual(component.url, expected_url)
        self.admin_settings.press_releases_index_page = None
        self.admin_settings.save()

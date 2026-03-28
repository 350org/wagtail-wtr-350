"""
Tests for concrete page models: HomePage, ContentPage, IndexPage.

WagtailPageTests covers parent/subpage type constraints.
TestCase with RequestFactory covers get_context() behaviour.
"""

from django.test import RequestFactory, TestCase
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTests

from wtrx.models import (
    ContentPage,
    FormPage,
    HomePage,
    IndexPage,
    ITEMS_PER_PAGE,
)


# ---------------------------------------------------------------------------
# HomePage
# ---------------------------------------------------------------------------


class TestHomePageParentSubpageTypes(WagtailPageTests):
    """HomePage can only be created under the Wagtail root page."""

    def test_can_create_under_root(self):
        self.assertCanCreateAt(Page, HomePage)

    def test_can_not_create_under_home_page(self):
        self.assertCanNotCreateAt(HomePage, HomePage)

    def test_can_not_create_under_content_page(self):
        self.assertCanNotCreateAt(ContentPage, HomePage)

    def test_allowed_subpage_types(self):
        self.assertAllowedSubpageTypes(HomePage, [ContentPage, IndexPage, FormPage])


class TestHomePageGetContext(TestCase):
    """HomePage.get_context() must populate the hero dict correctly."""

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(
            title="Home",
            slug="home-test-hpgc",
            hero_headline="Welcome",
            hero_copy="<p>Subtext</p>",
            hero_link_text="Learn more",
            hero_link_url="https://example.com",
        )
        root.add_child(instance=cls.home)

    def _get_context(self, page):
        request = RequestFactory().get("/")
        return page.get_context(request)

    def test_hero_headline_uses_custom_headline(self):
        ctx = self._get_context(self.home)
        self.assertEqual(ctx["hero"]["headline"], "Welcome")

    def test_hero_headline_falls_back_to_title(self):
        """When hero_headline is blank, headline falls back to page title."""
        original = self.home.hero_headline
        try:
            self.home.hero_headline = ""
            ctx = self._get_context(self.home)
            self.assertEqual(ctx["hero"]["headline"], self.home.title)
        finally:
            self.home.hero_headline = original

    def test_hero_copy_is_passed(self):
        ctx = self._get_context(self.home)
        self.assertEqual(ctx["hero"]["copy"], "<p>Subtext</p>")

    def test_hero_copy_is_block_is_false(self):
        ctx = self._get_context(self.home)
        self.assertFalse(ctx["hero"]["copy_is_block"])

    def test_hero_link_url_is_passed(self):
        ctx = self._get_context(self.home)
        self.assertEqual(ctx["hero"]["link_url"], "https://example.com")

    def test_hero_image_defaults_none(self):
        ctx = self._get_context(self.home)
        self.assertIsNone(ctx["hero"]["image"])

    def test_hero_video_defaults_none(self):
        ctx = self._get_context(self.home)
        self.assertIsNone(ctx["hero"]["video"])

    def test_hero_link_page_defaults_none(self):
        ctx = self._get_context(self.home)
        self.assertIsNone(ctx["hero"]["link_page"])

    def test_hero_dict_has_all_required_keys(self):
        ctx = self._get_context(self.home)
        required_keys = {
            "headline",
            "copy",
            "copy_is_block",
            "image",
            "video",
            "link_text",
            "link_page",
            "link_url",
        }
        self.assertEqual(set(ctx["hero"].keys()), required_keys)


class TestHomePageMeta(TestCase):
    """HomePage model Meta attributes."""

    def test_verbose_name(self):
        self.assertEqual(HomePage._meta.verbose_name, "home page")

    def test_verbose_name_plural(self):
        self.assertEqual(HomePage._meta.verbose_name_plural, "home pages")


# ---------------------------------------------------------------------------
# ContentPage
# ---------------------------------------------------------------------------


class TestContentPageParentSubpageTypes(WagtailPageTests):
    """ContentPage parent/subpage type constraints."""

    def test_can_create_under_home_page(self):
        self.assertCanCreateAt(HomePage, ContentPage)

    def test_can_create_under_content_page(self):
        self.assertCanCreateAt(ContentPage, ContentPage)

    def test_can_create_under_index_page(self):
        self.assertCanCreateAt(IndexPage, ContentPage)

    def test_can_not_create_under_root(self):
        self.assertCanNotCreateAt(Page, ContentPage)

    def test_allowed_subpage_types(self):
        self.assertAllowedSubpageTypes(ContentPage, [ContentPage, IndexPage, FormPage])


class TestContentPageGetContext(TestCase):
    """ContentPage.get_context() must populate the hero dict correctly."""

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-cp")
        root.add_child(instance=cls.home)
        cls.page = ContentPage(
            title="About Us",
            slug="about",
            hero_headline="Our Story",
            hero_link_text="Contact",
            hero_link_url="https://example.com/contact",
        )
        cls.home.add_child(instance=cls.page)

    def _get_context(self, page):
        request = RequestFactory().get("/")
        return page.get_context(request)

    def test_hero_headline_uses_custom(self):
        ctx = self._get_context(self.page)
        self.assertEqual(ctx["hero"]["headline"], "Our Story")

    def test_hero_headline_falls_back_to_title(self):
        original = self.page.hero_headline
        try:
            self.page.hero_headline = ""
            ctx = self._get_context(self.page)
            self.assertEqual(ctx["hero"]["headline"], "About Us")
        finally:
            self.page.hero_headline = original

    def test_copy_is_block_is_false(self):
        ctx = self._get_context(self.page)
        self.assertFalse(ctx["hero"]["copy_is_block"])

    def test_hero_video_defaults_none(self):
        ctx = self._get_context(self.page)
        self.assertIsNone(ctx["hero"]["video"])

    def test_hero_dict_keys(self):
        ctx = self._get_context(self.page)
        expected = {
            "headline",
            "copy",
            "copy_is_block",
            "image",
            "video",
            "link_text",
            "link_page",
            "link_url",
        }
        self.assertEqual(set(ctx["hero"].keys()), expected)


class TestContentPageMeta(TestCase):
    def test_verbose_name(self):
        self.assertEqual(ContentPage._meta.verbose_name, "content page")

    def test_verbose_name_plural(self):
        self.assertEqual(ContentPage._meta.verbose_name_plural, "content pages")


# ---------------------------------------------------------------------------
# IndexPage
# ---------------------------------------------------------------------------


class TestIndexPageParentSubpageTypes(WagtailPageTests):
    """IndexPage parent/subpage type constraints."""

    def test_can_create_under_home_page(self):
        self.assertCanCreateAt(HomePage, IndexPage)

    def test_can_create_under_content_page(self):
        self.assertCanCreateAt(ContentPage, IndexPage)

    def test_can_create_under_index_page(self):
        self.assertCanCreateAt(IndexPage, IndexPage)

    def test_can_not_create_under_root(self):
        self.assertCanNotCreateAt(Page, IndexPage)

    def test_allowed_subpage_types(self):
        self.assertAllowedSubpageTypes(IndexPage, [ContentPage, IndexPage, FormPage])


class TestIndexPageGetContext(TestCase):
    """IndexPage.get_context() must populate hero + children + paginator."""

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-ip")
        root.add_child(instance=cls.home)
        cls.index = IndexPage(title="Blog", slug="blog")
        cls.home.add_child(instance=cls.index)

        # Create 3 live child pages
        for i in range(3):
            child = ContentPage(title=f"Post {i + 1}", slug=f"post-{i + 1}")
            cls.index.add_child(instance=child)

    def _get_context(self, page, query_string=""):
        request = RequestFactory().get("/", query_string)
        return page.get_context(request)

    def test_hero_dict_present(self):
        ctx = self._get_context(self.index)
        self.assertIn("hero", ctx)

    def test_children_in_context(self):
        ctx = self._get_context(self.index)
        self.assertIn("children", ctx)

    def test_paginator_in_context(self):
        ctx = self._get_context(self.index)
        self.assertIn("paginator", ctx)

    def test_children_count_matches_live_children(self):
        ctx = self._get_context(self.index)
        # Page object from Paginator; len() counts items on the current page
        self.assertEqual(len(ctx["children"].object_list), 3)

    def test_invalid_page_number_returns_page_1(self):
        ctx = self._get_context(self.index, {"page": "abc"})
        self.assertEqual(ctx["children"].number, 1)

    def test_out_of_range_page_returns_last_page(self):
        ctx = self._get_context(self.index, {"page": "9999"})
        paginator = ctx["paginator"]
        self.assertEqual(ctx["children"].number, paginator.num_pages)

    def test_items_per_page_constant(self):
        self.assertEqual(ITEMS_PER_PAGE, 12)


class TestIndexPageMeta(TestCase):
    def test_verbose_name(self):
        self.assertEqual(IndexPage._meta.verbose_name, "index page")

    def test_verbose_name_plural(self):
        self.assertEqual(IndexPage._meta.verbose_name_plural, "index pages")

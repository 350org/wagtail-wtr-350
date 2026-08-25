"""
Tests for custom template tags in wtrx_tags.py.
"""

from unittest.mock import MagicMock

from django.test import SimpleTestCase, TestCase
from wagtail.models import Page

from wtrx.site_settings import NavigationSettings
from wtrx.templatetags.wtrx_tags import nav_item_is_active, page_as_card


class TestPageAsCard(SimpleTestCase):
    """page_as_card converts a Wagtail Page object to the card dict shape."""

    def _make_page(self, title="Test Page", search_description="", hero_image=None, has_hero_image=True):
        """Return a minimal mock page with the attributes we need."""
        page = MagicMock()
        page.title = title
        page.search_description = search_description
        if has_hero_image:
            page.hero_image = hero_image
        else:
            # Simulate a page model without hero_image attribute
            del page.hero_image
        return page

    def test_heading_uses_page_title(self):
        page = self._make_page(title="Campaign Home")
        card = page_as_card(page)
        self.assertEqual(card["heading"], "Campaign Home")

    def test_description_uses_search_description(self):
        page = self._make_page(search_description="A brief description")
        card = page_as_card(page)
        self.assertEqual(card["description"], "A brief description")

    def test_description_empty_when_no_search_description(self):
        page = self._make_page(search_description="")
        card = page_as_card(page)
        self.assertEqual(card["description"], "")

    def test_image_from_hero_image_when_present(self):
        mock_image = MagicMock()
        page = self._make_page(hero_image=mock_image)
        card = page_as_card(page)
        self.assertIs(card["image"], mock_image)

    def test_image_none_when_hero_image_is_none(self):
        page = self._make_page(hero_image=None)
        card = page_as_card(page)
        self.assertIsNone(card["image"])

    def test_image_none_when_page_has_no_hero_image_attr(self):
        """Pages without HeroMixin don't have hero_image; getattr fallback must return None."""
        page = self._make_page(has_hero_image=False)
        card = page_as_card(page)
        self.assertIsNone(card["image"])

    def test_link_page_is_the_page_itself(self):
        page = self._make_page()
        card = page_as_card(page)
        self.assertIs(card["link_page"], page)

    def test_link_url_is_none(self):
        """link_url should be None (not empty string) for consistency with the rest of the codebase."""
        page = self._make_page()
        card = page_as_card(page)
        self.assertIsNone(card["link_url"])

    def test_returned_dict_has_all_card_keys(self):
        page = self._make_page()
        card = page_as_card(page)
        self.assertEqual(set(card.keys()), {"heading", "description", "image", "link_page", "link_url"})


class TestNavItemIsActive(TestCase):
    """
    nav_item_is_active drives the active-page underline in header.html
    (Figma nav, node 1:965). A nav item is active for the section the visitor
    is in, not just for an exact page match.

    Tree:
        home
        ├── about          (top-level internal link)
        ├── media          (submenu parent — not itself linked)
        │   └── blogs      (the submenu's only internal child)
        │       └── post
        └── elsewhere
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = Page(title="Home", slug="nav-active-home")
        root.add_child(instance=cls.home)
        cls.about = Page(title="About", slug="about")
        cls.home.add_child(instance=cls.about)
        cls.media = Page(title="Media", slug="media")
        cls.home.add_child(instance=cls.media)
        cls.blogs = Page(title="Blogs", slug="blogs")
        cls.media.add_child(instance=cls.blogs)
        cls.post = Page(title="Post", slug="post")
        cls.blogs.add_child(instance=cls.post)
        cls.elsewhere = Page(title="Elsewhere", slug="elsewhere")
        cls.home.add_child(instance=cls.elsewhere)

    def setUp(self):
        """
        Built per-test, not in setUpTestData: Django deep-copies class
        attributes between tests for isolation, and a StreamValue that was
        never bound to a saved field has no _stream_field to copy.
        """
        nav = NavigationSettings()
        nav.primary_navigation = [
            ("internal", {"text": "About", "page": self.about}),
            ("external", {"text": "Donate", "url": "https://example.org/"}),
            ("anchor", {"text": "Top", "anchor": "top"}),
            (
                "submenu",
                {
                    "text": "Media & Resources",
                    "links": [("internal", {"text": "Blogs", "page": self.blogs})],
                },
            ),
        ]
        self.internal, self.external, self.anchor, self.submenu = list(
            nav.primary_navigation
        )

    def _active(self, item, page):
        return nav_item_is_active({"page": page}, item)

    def test_internal_link_active_on_its_own_page(self):
        self.assertTrue(self._active(self.internal, self.about))

    def test_internal_link_inactive_elsewhere(self):
        self.assertFalse(self._active(self.internal, self.elsewhere))

    def test_submenu_active_on_a_child_link_page(self):
        self.assertTrue(self._active(self.submenu, self.blogs))

    def test_submenu_active_deep_under_a_child_link(self):
        """A blog post keeps its parent submenu underlined."""
        self.assertTrue(self._active(self.submenu, self.post))

    def test_submenu_inactive_elsewhere(self):
        self.assertFalse(self._active(self.submenu, self.elsewhere))

    def test_submenu_inactive_on_its_unlinked_parent_page(self):
        """
        "Media" is only a label — the submenu tracks its child links, not a
        page of its own, so visiting /media/ does not light it up.
        """
        self.assertFalse(self._active(self.submenu, self.media))

    def test_external_and_anchor_links_are_never_active(self):
        for item in (self.external, self.anchor):
            with self.subTest(block_type=item.block_type):
                self.assertFalse(self._active(item, self.about))

    def test_no_current_page_is_never_active(self):
        """Views without a `page` in context (search, 404) underline nothing."""
        self.assertFalse(nav_item_is_active({}, self.internal))

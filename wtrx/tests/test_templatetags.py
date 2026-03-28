"""
Tests for custom template tags in wtrx_tags.py.
"""

from unittest.mock import MagicMock

from django.test import SimpleTestCase

from wtrx.templatetags.wtrx_tags import page_as_card


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

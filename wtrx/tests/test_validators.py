"""
Tests for wtrx/validators.py -- the shared tag-balance checker used by both
RawHTMLBlock.clean() (wtrx/blocks/__init__.py, StreamField content) and
IntegrationSettings.custom_head_html/custom_body_html (wtrx/site_settings.py,
plain model fields). Relocated here from wtrx/blocks/__init__.py specifically
so site_settings.py could reuse it without a circular import (blocks/__init__.py
already imports IntegrationSettings from site_settings.py) -- see the module's
own docstring.
"""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from wtrx.validators import html_is_balanced, validate_balanced_html, validate_url_or_query_string


class TestHtmlIsBalanced(SimpleTestCase):
    def test_balanced_tags(self):
        self.assertTrue(html_is_balanced("<div><p>Hello</p></div>"))

    def test_empty_string(self):
        self.assertTrue(html_is_balanced(""))

    def test_void_elements_need_no_closing_tag(self):
        self.assertTrue(html_is_balanced("<div><img src=\"x.png\"><br><hr></div>"))

    def test_unclosed_tag(self):
        self.assertFalse(html_is_balanced("<div><span></div>"))

    def test_stray_closing_tag(self):
        self.assertFalse(html_is_balanced("<div></div></span>"))

    def test_mismatched_nesting(self):
        self.assertFalse(html_is_balanced("<div><span></div></span>"))

    def test_inline_script_content_is_not_parsed_as_tags(self):
        """
        HTMLParser doesn't descend into <script>/<style> content as tags,
        so a "<"/">" inside inline JS (e.g. a comparison operator) must not
        be mistaken for a stray tag -- the exact false-positive risk a
        script-embed field (custom_head_html, GTM's own snippets) would
        otherwise hit constantly.
        """
        self.assertTrue(
            html_is_balanced("<script>if (a < b) { console.log('ok > done'); }</script>")
        )


class TestValidateBalancedHtml(SimpleTestCase):
    def test_balanced_html_does_not_raise(self):
        validate_balanced_html("<div><p>Hello</p></div>")

    def test_blank_does_not_raise(self):
        validate_balanced_html("")

    def test_unbalanced_html_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            validate_balanced_html("<div><span></div>")


class TestValidateUrlOrQueryString(SimpleTestCase):
    def test_accepts_full_urls_and_query_strings(self):
        for value in (
            "https://350.org/donate",
            "http://example.com/?form=FUNX",
            "?form=FUNYEKJXZJF",
            "?form=FUNX&utm_source=nav",
        ):
            with self.subTest(value=value):
                validate_url_or_query_string(value)

    def test_rejects_anything_else(self):
        for value in ("?", "? form=FUNX", "/donate", "javascript:alert(1)", "ftp://example.com", "donate"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_url_or_query_string(value)

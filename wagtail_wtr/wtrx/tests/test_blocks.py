"""
Tests for StreamField blocks.

Content blocks (ButtonBlock, VideoBlock), layout blocks (CalloutBlock,
HeroBlock), and action blocks (SignupLinkBlock) are tested here with
SimpleTestCase since their clean() methods don't require a database.

DonateBlock, SignupWagtailFormsBlock, and SignupActionNetworkBlock have no
custom clean() — their fields are validated by Wagtail's built-in block
validation, so no additional unit tests are needed here.
"""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from wagtail_wtr.wtrx.blocks import (
    ButtonBlock,
    CalloutBlock,
    HeroBlock,
    SignupLinkBlock,
    VideoBlock,
    _validate_at_most_one_link,
)


class TestButtonBlockValidation(SimpleTestCase):
    """ButtonBlock.clean() must enforce exactly one of link_page or link_url."""

    def _raw(self, link_url="", text="Click me", style="primary"):
        return {"text": text, "link_page": None, "link_url": link_url, "style": style}

    def test_valid_with_link_url(self):
        block = ButtonBlock()
        value = block.to_python(self._raw(link_url="https://example.com"))
        cleaned = block.clean(value)
        self.assertEqual(cleaned["link_url"], "https://example.com")

    def test_invalid_no_link_raises(self):
        block = ButtonBlock()
        value = block.to_python(self._raw())
        with self.assertRaises(ValidationError):
            block.clean(value)

    def test_all_styles_accepted(self):
        block = ButtonBlock()
        for style in ("primary", "secondary", "outline"):
            value = block.to_python(
                self._raw(link_url="https://example.com", style=style)
            )
            cleaned = block.clean(value)
            self.assertEqual(cleaned["style"], style)

    def test_text_is_required(self):
        block = ButtonBlock()
        value = block.to_python(
            {
                "text": "",
                "link_page": None,
                "link_url": "https://example.com",
                "style": "primary",
            }
        )
        with self.assertRaises(ValidationError):
            block.clean(value)


class TestVideoBlockValidation(SimpleTestCase):
    """VideoBlock.clean() must enforce exactly one of embed_url or media_file."""

    def _raw(self, embed_url="", caption=""):
        return {"embed_url": embed_url, "media_file": None, "caption": caption}

    def test_valid_with_embed_url(self):
        block = VideoBlock()
        value = block.to_python(
            self._raw(embed_url="https://www.youtube.com/watch?v=test")
        )
        cleaned = block.clean(value)
        self.assertEqual(cleaned["embed_url"], "https://www.youtube.com/watch?v=test")

    def test_invalid_neither_set_raises(self):
        block = VideoBlock()
        value = block.to_python(self._raw())
        with self.assertRaises(ValidationError):
            block.clean(value)

    def test_caption_is_optional(self):
        block = VideoBlock()
        value = block.to_python(
            self._raw(embed_url="https://www.youtube.com/watch?v=test")
        )
        cleaned = block.clean(value)
        self.assertEqual(cleaned["caption"], "")

    def test_caption_is_preserved(self):
        block = VideoBlock()
        value = block.to_python(
            self._raw(
                embed_url="https://www.youtube.com/watch?v=test",
                caption="My video caption",
            )
        )
        cleaned = block.clean(value)
        self.assertEqual(cleaned["caption"], "My video caption")


class TestCalloutBlockValidation(SimpleTestCase):
    """
    CalloutBlock uses _validate_at_most_one_link for its custom validation.

    CalloutBlock has a required ImageChooserBlock, so we cannot call
    block.clean() in SimpleTestCase (no DB). Instead we test the shared
    helper directly and verify the block's field structure.
    """

    def test_both_links_raises(self):
        errors = _validate_at_most_one_link(
            {"link_page": object(), "link_url": "https://example.com"}, {}
        )
        self.assertIn("link_page", errors)
        self.assertIn("link_url", errors)

    def test_only_link_url_no_error(self):
        errors = _validate_at_most_one_link(
            {"link_page": None, "link_url": "https://example.com"}, {}
        )
        self.assertEqual(errors, {})

    def test_only_link_page_no_error(self):
        errors = _validate_at_most_one_link({"link_page": object(), "link_url": ""}, {})
        self.assertEqual(errors, {})

    def test_neither_link_no_error(self):
        errors = _validate_at_most_one_link({"link_page": None, "link_url": ""}, {})
        self.assertEqual(errors, {})

    def test_block_has_expected_fields(self):
        block = CalloutBlock()
        self.assertIn("content", block.declared_blocks)
        self.assertIn("image", block.declared_blocks)
        self.assertIn("link_text", block.declared_blocks)
        self.assertIn("link_page", block.declared_blocks)
        self.assertIn("link_url", block.declared_blocks)
        self.assertIn("alignment", block.declared_blocks)

    def test_alignment_choices(self):
        block = CalloutBlock()
        choices = dict(block.declared_blocks["alignment"].field.choices)
        self.assertIn("image-left", choices)
        self.assertIn("image-right", choices)


class TestHeroBlockValidation(SimpleTestCase):
    """
    HeroBlock uses the same _validate_at_most_one_link helper.

    HeroBlock has an optional ImageChooserBlock but a required RichTextBlock
    whose content is hard to construct without a template context. We test
    the link validation helper directly and verify field structure.
    """

    def test_both_links_raises(self):
        errors = _validate_at_most_one_link(
            {"link_page": object(), "link_url": "https://example.com"}, {}
        )
        self.assertIn("link_page", errors)
        self.assertIn("link_url", errors)

    def test_only_link_url_no_error(self):
        errors = _validate_at_most_one_link(
            {"link_page": None, "link_url": "https://example.com"}, {}
        )
        self.assertEqual(errors, {})

    def test_block_has_expected_fields(self):
        block = HeroBlock()
        self.assertIn("headline", block.declared_blocks)
        self.assertIn("content", block.declared_blocks)
        self.assertIn("image", block.declared_blocks)
        self.assertIn("link_text", block.declared_blocks)
        self.assertIn("link_page", block.declared_blocks)
        self.assertIn("link_url", block.declared_blocks)

    def test_image_is_not_required(self):
        """The image field should be optional (required=False)."""
        block = HeroBlock()
        image_block = block.declared_blocks["image"]
        self.assertFalse(image_block.required)


class TestSignupLinkBlockValidation(SimpleTestCase):
    """SignupLinkBlock requires heading and external_url."""

    def _raw(self, heading="Sign Up", external_url="https://example.com"):
        return {
            "heading": heading,
            "description": "",
            "button_text": "",
            "external_url": external_url,
        }

    def test_valid(self):
        block = SignupLinkBlock()
        value = block.to_python(self._raw())
        cleaned = block.clean(value)
        self.assertEqual(cleaned["external_url"], "https://example.com")

    def test_heading_required(self):
        block = SignupLinkBlock()
        value = block.to_python(self._raw(heading=""))
        with self.assertRaises(ValidationError):
            block.clean(value)

    def test_external_url_required(self):
        block = SignupLinkBlock()
        value = block.to_python(self._raw(external_url=""))
        with self.assertRaises(ValidationError):
            block.clean(value)

    def test_button_text_optional(self):
        block = SignupLinkBlock()
        value = block.to_python(self._raw())
        cleaned = block.clean(value)
        self.assertEqual(cleaned["button_text"], "")

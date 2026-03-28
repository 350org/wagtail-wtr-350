"""
Tests for shared constants (wtrx/constants.py).
"""

from django.test import SimpleTestCase

from wtrx.constants import (
    CHARFIELD_MAX_LENGTH,
    RICHTEXT_FEATURES_FULL,
    RICHTEXT_FEATURES_HERO,
    RICHTEXT_FEATURES_INLINE,
)


class TestRichtextFeatureConstants(SimpleTestCase):
    """Verify the expected features in each rich text feature set."""

    def test_full_includes_headings(self):
        for heading in ("h2", "h3", "h4"):
            self.assertIn(heading, RICHTEXT_FEATURES_FULL)

    def test_full_includes_inline(self):
        for feat in ("bold", "italic", "link"):
            self.assertIn(feat, RICHTEXT_FEATURES_FULL)

    def test_full_includes_lists(self):
        self.assertIn("ol", RICHTEXT_FEATURES_FULL)
        self.assertIn("ul", RICHTEXT_FEATURES_FULL)

    def test_full_includes_blockquote(self):
        self.assertIn("blockquote", RICHTEXT_FEATURES_FULL)

    def test_inline_has_only_bold_italic_link(self):
        self.assertEqual(set(RICHTEXT_FEATURES_INLINE), {"bold", "italic", "link"})

    def test_hero_has_inline_plus_lists(self):
        self.assertEqual(
            set(RICHTEXT_FEATURES_HERO),
            {"bold", "italic", "link", "ol", "ul"},
        )

    def test_hero_has_no_headings(self):
        for heading in ("h2", "h3", "h4"):
            self.assertNotIn(heading, RICHTEXT_FEATURES_HERO)

    def test_hero_has_no_blockquote(self):
        self.assertNotIn("blockquote", RICHTEXT_FEATURES_HERO)

    def test_charfield_max_length(self):
        self.assertEqual(CHARFIELD_MAX_LENGTH, 255)


class TestConstantsUsedInBlocks(SimpleTestCase):
    """Verify that blocks import and use the shared constants."""

    def test_text_block_uses_full_features(self):
        from wtrx.blocks import TextBlock

        block = TextBlock()
        self.assertEqual(block.features, RICHTEXT_FEATURES_FULL)

    def test_body_stream_block_has_all_action_blocks(self):
        """All action block variants are registered in BodyStreamBlock."""
        from wtrx.blocks import BodyStreamBlock

        block = BodyStreamBlock()
        for name in (
            "donate",
            "signup_wagtail_forms",
            "signup_action_network",
            "signup_link",
        ):
            self.assertIn(name, block.child_blocks)

"""
Tests for StreamField blocks.

Content blocks (ButtonBlock, VideoBlock), layout blocks (CalloutBlock,
HeroBlock, SectionBlock), and action blocks (SignupLinkBlock,
SignupActionNetworkBlock) are tested here with SimpleTestCase since their
clean() methods don't require a database.

DonateBlock and SignupWagtailFormsBlock have no custom clean() — their fields
are validated by Wagtail's built-in block validation, so no additional unit
tests are needed here.
"""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from wtrx.blocks import (
    BodyStreamBlock,
    ButtonBlock,
    CalloutBlock,
    CardBlock,
    HeroBlock,
    SectionBlock,
    SectionContentBlock,
    SignupActionNetworkBlock,
    SignupLinkBlock,
    SuccessMessageBlock,
    VideoBlock,
    _validate_at_most_one_link,
    parse_action_network_url,
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


class TestSectionBlockStructure(SimpleTestCase):
    """
    SectionBlock.content must include all BodyStreamBlock block types except
    'section' itself (to prevent infinite nesting).
    """

    EXPECTED_BLOCK_NAMES = {
        "text",
        "image",
        "video",
        "button",
        "quote",
        "raw_html",
        "table",
        "card",
        "person_card",
        "card_grid",
        "accordion",
        "callout",
        "hero",
        "donate",
        "signup_wagtail_forms",
        "signup_action_network",
        "signup_link",
    }

    def test_content_block_names(self):
        block = SectionBlock()
        content_stream = block.declared_blocks["content"]
        registered = set(content_stream.child_blocks.keys())
        self.assertEqual(registered, self.EXPECTED_BLOCK_NAMES)

    def test_no_self_nesting(self):
        block = SectionBlock()
        content_stream = block.declared_blocks["content"]
        self.assertNotIn("section", content_stream.child_blocks)


class TestCardBlockFields(SimpleTestCase):
    """CardBlock field structure and icon optionality."""

    def test_has_icon_field(self):
        block = CardBlock()
        self.assertIn("icon", block.declared_blocks)

    def test_icon_is_optional(self):
        block = CardBlock()
        self.assertFalse(block.declared_blocks["icon"].required)

    def test_has_expected_fields(self):
        block = CardBlock()
        expected = {"icon", "heading", "description", "image", "link_page", "link_url"}
        self.assertEqual(set(block.declared_blocks.keys()), expected)

    def test_heading_is_required(self):
        block = CardBlock()
        self.assertTrue(block.declared_blocks["heading"].required)


class TestSectionContentBlockExtensibility(SimpleTestCase):
    """
    SectionContentBlock is a named StreamBlock subclass so forks can
    override individual child blocks via Wagtail's metaclass inheritance.
    """

    def test_is_subclassable(self):
        """Subclassing SectionContentBlock and overriding a block works."""
        from wagtail.blocks import CharBlock, StructBlock

        class CustomCard(StructBlock):
            title = CharBlock()

        class SiteSectionContent(SectionContentBlock):
            card = CustomCard()

        block = SiteSectionContent()
        # The override should replace CardBlock with CustomCard
        self.assertIsInstance(block.child_blocks["card"], CustomCard)
        # All other blocks should still be present
        self.assertIn("text", block.child_blocks)
        self.assertIn("donate", block.child_blocks)

    def test_body_stream_block_matches_section_content_plus_section(self):
        """BodyStreamBlock should have all SectionContentBlock types plus 'section'."""
        body = BodyStreamBlock()
        section_content = SectionContentBlock()
        body_names = set(body.child_blocks.keys())
        section_names = set(section_content.child_blocks.keys())
        self.assertEqual(body_names - section_names, {"section"})


# ---------------------------------------------------------------------------
# parse_action_network_url helper
# ---------------------------------------------------------------------------


class TestParseActionNetworkUrl(SimpleTestCase):
    """parse_action_network_url() extracts action_type and slug from AN URLs."""

    def test_basic_form_url(self):
        result = parse_action_network_url("https://actionnetwork.org/forms/join-30")
        self.assertEqual(result, {"action_type": "form", "slug": "join-30"})

    def test_url_with_query_params(self):
        result = parse_action_network_url(
            "https://actionnetwork.org/forms/join-30?source=direct_link&"
        )
        self.assertEqual(result, {"action_type": "form", "slug": "join-30"})

    def test_url_with_trailing_slash(self):
        result = parse_action_network_url("https://actionnetwork.org/forms/join-30/")
        self.assertEqual(result, {"action_type": "form", "slug": "join-30"})

    def test_url_with_www(self):
        result = parse_action_network_url(
            "https://www.actionnetwork.org/forms/my-signup"
        )
        self.assertEqual(result, {"action_type": "form", "slug": "my-signup"})

    def test_url_http(self):
        """HTTP URLs are accepted (URLBlock may normalise, but parser handles both)."""
        result = parse_action_network_url("http://actionnetwork.org/forms/test-form")
        self.assertEqual(result, {"action_type": "form", "slug": "test-form"})

    def test_invalid_domain_raises(self):
        with self.assertRaises(ValidationError) as cm:
            parse_action_network_url("https://example.com/forms/join-30")
        self.assertIn("Action Network URL", str(cm.exception.messages))

    def test_unsupported_action_type_raises(self):
        """Petitions are not yet supported — should raise a clear error."""
        with self.assertRaises(ValidationError) as cm:
            parse_action_network_url("https://actionnetwork.org/petitions/my-petition")
        # cm.exception.message is the uninterpolated template; use str() on the
        # exception itself which resolves params via __str__ → .messages.
        error_text = str(cm.exception.messages)
        self.assertIn("Unsupported", error_text)
        self.assertIn("petitions", error_text)

    def test_missing_slug_raises(self):
        with self.assertRaises(ValidationError) as cm:
            parse_action_network_url("https://actionnetwork.org/forms/")
        self.assertIn("form slug", str(cm.exception.messages))

    def test_missing_path_raises(self):
        with self.assertRaises(ValidationError):
            parse_action_network_url("https://actionnetwork.org/")

    def test_empty_string_raises(self):
        with self.assertRaises(ValidationError):
            parse_action_network_url("")

    def test_extra_path_segments_uses_first_two(self):
        """Extra segments after the slug should be ignored — only type and slug matter."""
        result = parse_action_network_url(
            "https://actionnetwork.org/forms/join-30/extra/segments"
        )
        self.assertEqual(result, {"action_type": "form", "slug": "join-30"})

    def test_slug_with_uppercase_rejected(self):
        """AN slugs are lowercase; uppercase characters should fail validation."""
        with self.assertRaises(ValidationError) as cm:
            parse_action_network_url("https://actionnetwork.org/forms/Join-30")
        self.assertIn("unexpected characters", str(cm.exception.messages))

    def test_slug_with_special_chars_rejected(self):
        """Slugs with special characters should fail validation."""
        with self.assertRaises(ValidationError) as cm:
            parse_action_network_url(
                "https://actionnetwork.org/forms/join<script>alert(1)</script>"
            )
        self.assertIn("unexpected characters", str(cm.exception.messages))

    def test_slug_starting_with_hyphen_rejected(self):
        """Slugs must start with alphanumeric, not a hyphen."""
        with self.assertRaises(ValidationError):
            parse_action_network_url("https://actionnetwork.org/forms/-bad-slug")


# ---------------------------------------------------------------------------
# SignupActionNetworkBlock validation and context
# ---------------------------------------------------------------------------


class TestSignupActionNetworkBlockValidation(SimpleTestCase):
    """SignupActionNetworkBlock.clean() validates the pasted Action Network URL."""

    def _raw(
        self, action_url="https://actionnetwork.org/forms/join-30", heading="Sign Up"
    ):
        return {
            "heading": heading,
            "description": "",
            "action_url": action_url,
            "success_message": "",
        }

    def test_valid_url_accepted(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(self._raw())
        cleaned = block.clean(value)
        self.assertEqual(
            cleaned["action_url"], "https://actionnetwork.org/forms/join-30"
        )

    def test_url_with_query_params_accepted(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(
            self._raw(
                action_url="https://actionnetwork.org/forms/join-30?source=direct_link&"
            )
        )
        cleaned = block.clean(value)
        self.assertIn("join-30", cleaned["action_url"])

    def test_invalid_domain_rejected(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(
            self._raw(action_url="https://example.com/forms/join-30")
        )
        with self.assertRaises(ValidationError):
            block.clean(value)

    def test_unsupported_action_type_rejected(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(
            self._raw(action_url="https://actionnetwork.org/petitions/my-petition")
        )
        with self.assertRaises(ValidationError):
            block.clean(value)

    def test_heading_required(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(self._raw(heading=""))
        with self.assertRaises(ValidationError):
            block.clean(value)

    def test_action_url_required(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(self._raw(action_url=""))
        with self.assertRaises(ValidationError):
            block.clean(value)

    def test_success_message_optional(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(self._raw())
        cleaned = block.clean(value)
        # SuccessMessageBlock (StreamBlock) — empty list → falsy StreamValue
        self.assertFalse(cleaned["success_message"])

    def test_has_expected_fields(self):
        block = SignupActionNetworkBlock()
        expected = {"heading", "description", "action_url", "success_message"}
        self.assertEqual(set(block.declared_blocks.keys()), expected)


class TestSignupActionNetworkBlockContext(SimpleTestCase):
    """SignupActionNetworkBlock.get_context() extracts action_type and slug."""

    def test_context_extracts_type_and_slug(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(
            {
                "heading": "Join",
                "description": "",
                "action_url": "https://actionnetwork.org/forms/join-30",
                "success_message": "",
            }
        )
        ctx = block.get_context(value)
        self.assertEqual(ctx["action_type"], "form")
        self.assertEqual(ctx["slug"], "join-30")

    def test_context_with_complex_slug(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(
            {
                "heading": "Join",
                "description": "",
                "action_url": "https://actionnetwork.org/forms/my-great-campaign-2026?source=widget",
                "success_message": "",
            }
        )
        ctx = block.get_context(value)
        self.assertEqual(ctx["slug"], "my-great-campaign-2026")

    def test_context_passes_success_message(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(
            {
                "heading": "Join",
                "description": "",
                "action_url": "https://actionnetwork.org/forms/join-30",
                "success_message": [
                    {"type": "text", "value": "<p>Thanks for signing up!</p>"}
                ],
            }
        )
        ctx = block.get_context(value)
        self.assertTrue(ctx["success_message"])

    def test_context_without_success_message(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(
            {
                "heading": "Join",
                "description": "",
                "action_url": "https://actionnetwork.org/forms/join-30",
                "success_message": [],
            }
        )
        ctx = block.get_context(value)
        # Empty StreamValue is falsy
        self.assertFalse(ctx["success_message"])

    def test_context_empty_url_degrades_gracefully(self):
        """When action_url is empty, context should have empty strings."""
        block = SignupActionNetworkBlock()
        value = block.to_python(
            {
                "heading": "Join",
                "description": "",
                "action_url": "",
                "success_message": "",
            }
        )
        ctx = block.get_context(value)
        self.assertEqual(ctx["action_type"], "")
        self.assertEqual(ctx["slug"], "")


# ---------------------------------------------------------------------------
# SuccessMessageBlock — legacy coercion
# ---------------------------------------------------------------------------


class TestSuccessMessageBlock(SimpleTestCase):
    """
    SuccessMessageBlock.to_python and bulk_to_python coerce legacy
    RichTextBlock string values (old format) to an empty StreamValue
    so that existing pages load without "string indices must be integers".
    """

    def test_empty_string_coerces_to_empty_stream(self):
        block = SuccessMessageBlock()
        result = block.to_python("")
        self.assertFalse(result)

    def test_html_string_coerces_to_empty_stream(self):
        """Old RichTextBlock data stored "<p>...</p>" — must not crash."""
        block = SuccessMessageBlock()
        result = block.to_python("<p>Thanks for signing up!</p>")
        self.assertFalse(result)

    def test_none_coerces_to_empty_stream(self):
        block = SuccessMessageBlock()
        result = block.to_python(None)
        self.assertFalse(result)

    def test_valid_list_passes_through(self):
        block = SuccessMessageBlock()
        result = block.to_python(
            [{"type": "text", "value": "<p>Thanks!</p>", "id": "abc123"}]
        )
        self.assertTrue(result)

    def test_bulk_to_python_with_legacy_strings(self):
        """bulk_to_python is called by Wagtail when loading revisions."""
        block = SuccessMessageBlock()
        results = block.bulk_to_python(["", "<p>Old rich text value</p>", []])
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertFalse(r)  # all coerced to empty StreamValue

    def test_bulk_to_python_with_valid_list(self):
        block = SuccessMessageBlock()
        results = block.bulk_to_python(
            [
                [{"type": "text", "value": "<p>Thanks!</p>", "id": "abc123"}],
                [],
            ]
        )
        self.assertTrue(results[0])
        self.assertFalse(results[1])

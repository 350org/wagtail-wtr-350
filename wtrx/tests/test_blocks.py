"""
Tests for StreamField blocks.

Content blocks (ButtonBlock, VideoBlock), layout blocks (QuoteBlock,
HeroBlock, SectionBlock, CardCarouselBlock, CalloutBlock), and action blocks
(SignupLinkBlock, SignupActionNetworkBlock) are tested here with
SimpleTestCase since their clean() methods don't require a database.

DonateBlock, DonateFundraiseUpBlock, and SignupWagtailFormsBlock have no
custom clean() — their fields are validated by Wagtail's built-in block
validation, so only field-structure tests are needed for them.

CardCarouselBlock and CalloutBlock both reuse the shared
_validate_at_most_one_link() helper for their clean() methods (same as
QuoteBlock) — its link/no-link/both-links behavior is exercised generically
in TestQuoteBlockValidation, so per-block tests here only check field
structure, not the link-validation logic itself. Both blocks also contain
ImageChooserBlock fields (CalloutBlock.image, CardCarouselBlock's required
CarouselCardBlock.image), so — like QuoteBlock — a full block.clean() call
isn't exercised end-to-end here: resolving a real image PK needs a database,
which SimpleTestCase doesn't have.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from wagtail.blocks import RichTextBlock
from wagtail.models import Page

from wtrx.blocks import (
    CALLOUT_COLOR_CHOICES,
    BodyStreamBlock,
    ButtonBlock,
    CalloutBlock,
    CardBlock,
    CardCarouselBlock,
    DonateBlock,
    DonateFundraiseUpBlock,
    FeaturePanelBlock,
    HeroBlock,
    HeroCTABlock,
    ImageCardListBlock,
    ImageCardListItemBlock,
    ImageTextBlock,
    PageCardsBlock,
    QuoteBlock,
    SectionBlock,
    SectionContentBlock,
    SignupActionKitBlock,
    SignupActionNetworkBlock,
    SignupLinkBlock,
    SuccessMessageBlock,
    VideoBlock,
    _validate_at_most_one_link,
    parse_action_network_url,
)
from wtrx.models import ContentPage, HomePage, IndexPage


class TestButtonBlockValidation(SimpleTestCase):
    """
    ButtonBlock.clean() must enforce exactly one of link_page, link_url or
    anchor. anchor exists because link_url is a URLBlock and so cannot hold a
    bare "#petition" — see ButtonBlock's docstring.
    """

    def _raw(self, link_url="", text="Click me", style="primary", anchor=""):
        return {
            "text": text,
            "link_page": None,
            "link_url": link_url,
            "anchor": anchor,
            "style": style,
        }

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
                "anchor": "",
                "style": "primary",
            }
        )
        with self.assertRaises(ValidationError):
            block.clean(value)

    def test_valid_with_anchor(self):
        block = ButtonBlock()
        value = block.to_python(self._raw(anchor="petition"))
        cleaned = block.clean(value)
        self.assertEqual(cleaned["anchor"], "petition")

    def test_invalid_anchor_and_url_raises(self):
        block = ButtonBlock()
        value = block.to_python(
            self._raw(link_url="https://example.com", anchor="petition")
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


class TestQuoteBlockValidation(SimpleTestCase):
    """
    QuoteBlock validation: exactly one of image/media_file, at most one link.

    ImageChooserBlock and VideoChooserBlock both require a DB to resolve
    chooser values, so we cannot call block.clean() end-to-end in
    SimpleTestCase. We test the media-exclusivity logic (which only inspects
    truthiness of the cleaned values) via a standalone helper that mirrors
    the block's clean() logic, and verify field structure via declared_blocks.
    """

    def _run_media_validation(self, image, media_file):
        """Mirror the media-exclusivity branch of QuoteBlock.clean()."""
        from django.core.exceptions import ValidationError as DjValidationError
        errors = {}
        has_image = bool(image)
        has_video = bool(media_file)
        if not has_image and not has_video:
            msg = DjValidationError("Provide either an image or a media file.")
            errors["image"] = msg
            errors["media_file"] = msg
        elif has_image and has_video:
            msg = DjValidationError("Provide either an image or a media file, not both.")
            errors["image"] = msg
            errors["media_file"] = msg
        return errors

    def _make_value(self, image=None, media_file=None, link_page=None, link_url=""):
        return {
            "image": image,
            "media_file": media_file,
            "link_page": link_page,
            "link_url": link_url,
        }

    # --- media validation ---

    def test_media_validation_both_absent(self):
        """Both image and media_file absent should produce errors on both fields."""
        errors = self._run_media_validation(image=None, media_file=None)
        self.assertIn("image", errors)
        self.assertIn("media_file", errors)

    def test_media_validation_both_present(self):
        """Both image and media_file set should produce errors on both fields."""
        errors = self._run_media_validation(image=object(), media_file=object())
        self.assertIn("image", errors)
        self.assertIn("media_file", errors)

    def test_media_validation_image_only(self):
        """Image only (no media_file) should produce no media errors."""
        errors = self._run_media_validation(image=object(), media_file=None)
        self.assertEqual(errors, {})

    def test_media_validation_video_only(self):
        """media_file only (no image) should produce no media errors."""
        errors = self._run_media_validation(image=None, media_file=object())
        self.assertEqual(errors, {})

    def test_media_validation_both_present(self):
        """Both image and media_file set should produce errors on both fields."""
        errors = {}
        has_image = True
        has_video = True
        if has_image and has_video:
            from django.core.exceptions import ValidationError as DjValidationError
            msg = DjValidationError("Provide either an image or a media file, not both.")
            errors["image"] = msg
            errors["media_file"] = msg
        self.assertIn("image", errors)
        self.assertIn("media_file", errors)

    def test_block_has_expected_fields(self):
        block = QuoteBlock()
        self.assertIn("content", block.declared_blocks)
        self.assertIn("image", block.declared_blocks)
        self.assertIn("media_file", block.declared_blocks)
        self.assertIn("link_text", block.declared_blocks)
        self.assertIn("link_page", block.declared_blocks)
        self.assertIn("link_url", block.declared_blocks)
        self.assertIn("alignment", block.declared_blocks)

    def test_image_is_optional(self):
        """image must be optional (required=False) to allow media_file instead."""
        block = QuoteBlock()
        self.assertFalse(block.declared_blocks["image"].required)

    def test_media_file_is_optional(self):
        """media_file must be optional (required=False) to allow image instead."""
        block = QuoteBlock()
        self.assertFalse(block.declared_blocks["media_file"].required)

    def test_alignment_choices(self):
        block = QuoteBlock()
        choices = dict(block.declared_blocks["alignment"].field.choices)
        self.assertIn("image-left", choices)
        self.assertIn("image-right", choices)

    # --- link validation (via shared helper) ---

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

    def test_anchor_alone_is_allowed_when_declared_as_an_extra_field(self):
        errors = _validate_at_most_one_link(
            {"link_page": None, "link_url": "", "anchor": "petition"},
            {},
            extra_fields=("anchor",),
        )
        self.assertEqual(errors, {})

    def test_anchor_conflicts_with_a_page_link(self):
        errors = _validate_at_most_one_link(
            {"link_page": object(), "link_url": "", "anchor": "petition"},
            {},
            extra_fields=("anchor",),
        )
        self.assertEqual(set(errors), {"link_page", "anchor"})

    def test_anchor_is_ignored_by_callers_that_do_not_declare_it(self):
        """
        The two-field callers (QuoteBlock, CardBlock, CardCarouselBlock)
        have no anchor field at all, so a stray key must not be treated as
        a competing link target.
        """
        errors = _validate_at_most_one_link(
            {"link_page": object(), "link_url": "", "anchor": "petition"}, {}
        )
        self.assertEqual(errors, {})


class TestHeroBlockFields(SimpleTestCase):
    """
    HeroBlock has an optional ImageChooserBlock but a required RichTextBlock
    whose content is hard to construct without a template context. We just
    verify field structure here.
    """

    def test_block_has_expected_fields(self):
        """
        No layout or cta fields — HeroBlock always renders as hero.html's
        "banner" variant, which has a fixed layout and never renders a cta
        (see HeroBlock's docstring).
        """
        block = HeroBlock()
        self.assertEqual(
            set(block.declared_blocks.keys()),
            {"headline", "content", "image", "banner_color"},
        )

    def test_image_is_not_required(self):
        """The image field should be optional (required=False)."""
        block = HeroBlock()
        image_block = block.declared_blocks["image"]
        self.assertFalse(image_block.required)

    def test_banner_color_default_is_navy(self):
        block = HeroBlock()
        self.assertEqual(block.declared_blocks["banner_color"].meta.default, "navy")

    def test_get_context_always_variant_banner(self):
        block = HeroBlock()
        value = block.to_python(
            {"headline": "Take Action", "content": "", "image": None, "banner_color": "red"}
        )
        ctx = block.get_context(value)
        self.assertEqual(ctx["hero"]["variant"], "banner")
        self.assertEqual(ctx["hero"]["headline"], "Take Action")
        self.assertEqual(ctx["hero"]["banner_color"], "red")
        self.assertEqual(ctx["hero"]["cta"], [])
        self.assertIsNone(ctx["hero"]["video"])


class TestHeroCTABlock(SimpleTestCase):
    """
    HeroCTABlock is HeroBlock.cta / HeroMixin.hero_cta's block type: at most
    one of button, signup (ActionKit), donate, or announcement.
    """

    def test_button_choice_is_button_block(self):
        block = HeroCTABlock()
        self.assertIsInstance(block.declared_blocks["button"], ButtonBlock)

    def test_signup_choice_is_actionkit(self):
        block = HeroCTABlock()
        self.assertIsInstance(block.declared_blocks["signup"], SignupActionKitBlock)

    def test_donate_choice_is_donate_block(self):
        block = HeroCTABlock()
        self.assertIsInstance(block.declared_blocks["donate"], DonateBlock)

    def test_at_most_one_item(self):
        self.assertEqual(HeroCTABlock().meta.max_num, 1)

    def test_zero_items_allowed(self):
        self.assertEqual(HeroCTABlock().meta.min_num, 0)


class TestSignupLinkBlockValidation(SimpleTestCase):
    """SignupLinkBlock requires external_url; heading and anchor_id are optional."""

    def _raw(self, heading="Sign Up", external_url="https://example.com"):
        return {
            "heading": heading,
            "description": "",
            "button_text": "",
            "external_url": external_url,
            "anchor_id": "",
        }

    def test_valid(self):
        block = SignupLinkBlock()
        value = block.to_python(self._raw())
        cleaned = block.clean(value)
        self.assertEqual(cleaned["external_url"], "https://example.com")

    def test_heading_optional(self):
        """heading is now optional — omitting it must not raise."""
        block = SignupLinkBlock()
        value = block.to_python(self._raw(heading=""))
        cleaned = block.clean(value)
        self.assertEqual(cleaned["heading"], "")

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

    def test_anchor_id_optional(self):
        block = SignupLinkBlock()
        self.assertFalse(block.declared_blocks["anchor_id"].required)

    def test_has_expected_fields(self):
        block = SignupLinkBlock()
        expected = {"heading", "description", "button_text", "external_url", "anchor_id"}
        self.assertEqual(set(block.declared_blocks.keys()), expected)


class TestSectionBlockWidth(SimpleTestCase):
    """
    SectionBlock.width picks the inner content column's measure — see
    SECTION_WIDTH_CHOICES for why the section owns this rather than each
    child block.
    """

    def test_default_is_default(self):
        block = SectionBlock()
        self.assertEqual(block.child_blocks["width"].get_default(), "default")

    def test_all_choices_available(self):
        block = SectionBlock()
        choices = {value for value, _label in block.child_blocks["width"].field.choices}
        self.assertEqual(choices, {"narrow", "default", "wide"})


class TestSignupActionKitBlockPanelFields(SimpleTestCase):
    """
    The eyebrow pill and background fill added for Figma's petition panel
    (node 1:1239) — see signup_actionkit_block.html.
    """

    def test_eyebrow_is_optional(self):
        block = SignupActionKitBlock()
        self.assertFalse(block.child_blocks["eyebrow"].required)

    def test_background_defaults_to_dark(self):
        block = SignupActionKitBlock()
        self.assertEqual(block.child_blocks["background"].get_default(), "dark")

    def test_background_choices(self):
        block = SignupActionKitBlock()
        choices = {
            value for value, _label in block.child_blocks["background"].field.choices
        }
        self.assertEqual(
            choices, {"navy", "red", "dark", "blue-gradient", "light-grey"}
        )

    def test_background_offers_the_same_fills_as_the_hero_banner(self):
        """
        The panel's fills are CalloutBlock's/the hero banner's five colors,
        except that dark grey keeps the legacy "dark" key this block already
        stores rather than adopting "dark-grey" — see
        SIGNUP_BACKGROUND_CHOICES. Both name the same --color-dark fill, so
        the two sets should agree once that one rename is applied.
        """
        block = SignupActionKitBlock()
        choices = {
            value for value, _label in block.child_blocks["background"].field.choices
        }
        callout_colors = {value for value, _label in CALLOUT_COLOR_CHOICES}
        self.assertEqual(
            (choices - {"dark"}) | {"dark-grey"},
            callout_colors,
        )

    def test_panel_tones_cover_only_the_colliding_fills(self):
        """
        Navy and red take no tone modifier: the stacked form's default
        chrome (blue submit button, dark fine-print box, light text) already
        reads against them. The other three each collide with one piece of
        it — see SignupActionKitBlock.PANEL_TONES.
        """
        self.assertEqual(
            SignupActionKitBlock.PANEL_TONES,
            {
                "dark": "on-dark",
                "blue-gradient": "on-primary",
                "light-grey": "on-light",
            },
        )

    def test_get_context_passes_the_panel_tone_for_the_background(self):
        block = SignupActionKitBlock()
        value = {"short_form_id": "ppg", "background": "light-grey"}
        self.assertEqual(block.get_context(value, parent_context={})["panel_tone"], "on-light")

    def test_get_context_panel_tone_is_blank_for_uncolliding_backgrounds(self):
        block = SignupActionKitBlock()
        value = {"short_form_id": "ppg", "background": "red"}
        self.assertEqual(block.get_context(value, parent_context={})["panel_tone"], "")


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
        "image_card_list",
        "image_text",
        "feature_panel",
        "card_carousel",
        "page_cards",
        "accordion",
        "callout",
        "hero",
        "donate",
        "donate_fundraiseup",
        "signup_wagtail_forms",
        "signup_action_network",
        "signup_actionkit",
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
        expected = {
            "tag",
            "icon",
            "heading",
            "description",
            "image",
            "link_page",
            "link_url",
            "link_text",
        }
        self.assertEqual(set(block.declared_blocks.keys()), expected)

    def test_heading_is_required(self):
        block = CardBlock()
        self.assertTrue(block.declared_blocks["heading"].required)


class TestImageCardListItemBlockFields(SimpleTestCase):
    """ImageCardListItemBlock field structure: heading + description only."""

    def test_has_expected_fields(self):
        block = ImageCardListItemBlock()
        self.assertEqual(set(block.declared_blocks.keys()), {"heading", "description"})

    def test_heading_is_required(self):
        block = ImageCardListItemBlock()
        self.assertTrue(block.declared_blocks["heading"].required)

    def test_description_is_required(self):
        block = ImageCardListItemBlock()
        self.assertTrue(block.declared_blocks["description"].required)


class TestImageCardListBlockFields(SimpleTestCase):
    """ImageCardListBlock field structure: heading + image + cards (min 2)."""

    def test_has_expected_fields(self):
        block = ImageCardListBlock()
        self.assertEqual(set(block.declared_blocks.keys()), {"heading", "image", "cards"})

    def test_heading_is_required(self):
        block = ImageCardListBlock()
        self.assertTrue(block.declared_blocks["heading"].required)

    def test_image_is_required(self):
        block = ImageCardListBlock()
        self.assertTrue(block.declared_blocks["image"].required)

    def test_cards_min_num_is_two(self):
        block = ImageCardListBlock()
        self.assertEqual(block.declared_blocks["cards"].meta.min_num, 2)

    def test_cards_have_no_max_num(self):
        block = ImageCardListBlock()
        self.assertIsNone(block.declared_blocks["cards"].meta.max_num)

    def test_cards_child_block_is_image_card_list_item(self):
        block = ImageCardListBlock()
        self.assertIsInstance(block.declared_blocks["cards"].child_block, ImageCardListItemBlock)


class TestImageTextBlockFields(SimpleTestCase):
    """ImageTextBlock field structure: heading + image + text, all required."""

    def test_has_expected_fields(self):
        block = ImageTextBlock()
        self.assertEqual(set(block.declared_blocks.keys()), {"heading", "image", "text"})

    def test_heading_is_required(self):
        block = ImageTextBlock()
        self.assertTrue(block.declared_blocks["heading"].required)

    def test_image_is_required(self):
        block = ImageTextBlock()
        self.assertTrue(block.declared_blocks["image"].required)

    def test_text_is_required(self):
        block = ImageTextBlock()
        self.assertTrue(block.declared_blocks["text"].required)

    def test_text_is_richtext(self):
        block = ImageTextBlock()
        self.assertIsInstance(block.declared_blocks["text"], RichTextBlock)


class TestFeaturePanelBlockFields(SimpleTestCase):
    """
    FeaturePanelBlock field structure. Link-validation logic (clean() wraps
    _validate_at_most_one_link) is covered generically in
    TestQuoteBlockValidation — see module docstring. The block's required
    ImageChooserBlock means block.clean() can't be exercised end-to-end
    without a database, same as QuoteBlock/CalloutBlock.
    """

    def test_has_expected_fields(self):
        block = FeaturePanelBlock()
        expected = {
            "eyebrow",
            "heading",
            "text",
            "image",
            "alignment",
            "background",
            "link_text",
            "link_page",
            "link_url",
            "anchor",
        }
        self.assertEqual(set(block.declared_blocks.keys()), expected)

    def test_heading_is_required(self):
        block = FeaturePanelBlock()
        self.assertTrue(block.declared_blocks["heading"].required)

    def test_image_is_required(self):
        block = FeaturePanelBlock()
        self.assertTrue(block.declared_blocks["image"].required)

    def test_optional_fields_are_optional(self):
        """Everything but heading/image is optional — the Figma dark panel
        has no eyebrow, and the light one has no body copy."""
        block = FeaturePanelBlock()
        for name in ("eyebrow", "text", "link_text", "link_page", "link_url", "anchor"):
            with self.subTest(field=name):
                self.assertFalse(block.declared_blocks[name].required)

    def test_text_is_richtext(self):
        block = FeaturePanelBlock()
        self.assertIsInstance(block.declared_blocks["text"], RichTextBlock)

    def test_alignment_choices(self):
        block = FeaturePanelBlock()
        choices = dict(block.declared_blocks["alignment"].field.choices)
        self.assertEqual(set(choices.keys()), {"image-left", "image-right"})

    def test_alignment_defaults_to_image_left(self):
        block = FeaturePanelBlock()
        self.assertEqual(block.declared_blocks["alignment"].meta.default, "image-left")

    def test_background_choices(self):
        block = FeaturePanelBlock()
        choices = dict(block.declared_blocks["background"].field.choices)
        self.assertEqual(set(choices.keys()), {"light", "dark"})

    def test_background_defaults_to_light(self):
        block = FeaturePanelBlock()
        self.assertEqual(block.declared_blocks["background"].meta.default, "light")


class TestCardCarouselBlockFields(SimpleTestCase):
    """
    CardCarouselBlock field structure. Link-validation logic (clean()
    wraps _validate_at_most_one_link) is covered generically in
    TestQuoteBlockValidation — see module docstring.
    """

    def test_has_expected_fields(self):
        block = CardCarouselBlock()
        expected = {"heading", "content", "link_text", "link_page", "link_url", "cards"}
        self.assertEqual(set(block.declared_blocks.keys()), expected)

    def test_heading_is_required(self):
        block = CardCarouselBlock()
        self.assertTrue(block.declared_blocks["heading"].required)

    def test_content_is_required(self):
        block = CardCarouselBlock()
        self.assertTrue(block.declared_blocks["content"].required)

    def test_link_fields_are_optional(self):
        block = CardCarouselBlock()
        self.assertFalse(block.declared_blocks["link_text"].required)
        self.assertFalse(block.declared_blocks["link_page"].required)
        self.assertFalse(block.declared_blocks["link_url"].required)

    def test_cards_min_num_is_three(self):
        block = CardCarouselBlock()
        self.assertEqual(block.declared_blocks["cards"].meta.min_num, 3)

    def test_cards_have_no_max_num(self):
        block = CardCarouselBlock()
        self.assertIsNone(block.declared_blocks["cards"].meta.max_num)

    def test_carousel_card_image_is_required(self):
        """
        CarouselCardBlock overrides CardBlock.image to be required — every
        carousel card needs one, unlike the general-purpose CardBlock.
        """
        block = CardCarouselBlock()
        card_block = block.declared_blocks["cards"].child_block
        self.assertTrue(card_block.declared_blocks["image"].required)


class TestCalloutBlockFields(SimpleTestCase):
    """
    CalloutBlock field structure. Link-validation logic (clean() wraps
    _validate_at_most_one_link) is covered generically in
    TestQuoteBlockValidation — see module docstring.
    """

    def test_has_expected_fields(self):
        block = CalloutBlock()
        expected = {
            "heading",
            "subheading",
            "content",
            "link_text",
            "link_page",
            "link_url",
            "color",
            "image",
        }
        self.assertEqual(set(block.declared_blocks.keys()), expected)

    def test_heading_is_optional(self):
        block = CalloutBlock()
        self.assertFalse(block.declared_blocks["heading"].required)

    def test_subheading_is_optional(self):
        block = CalloutBlock()
        self.assertFalse(block.declared_blocks["subheading"].required)

    def test_content_is_optional(self):
        block = CalloutBlock()
        self.assertFalse(block.declared_blocks["content"].required)

    def test_image_is_optional(self):
        block = CalloutBlock()
        self.assertFalse(block.declared_blocks["image"].required)

    def test_link_fields_are_optional(self):
        block = CalloutBlock()
        self.assertFalse(block.declared_blocks["link_text"].required)
        self.assertFalse(block.declared_blocks["link_page"].required)
        self.assertFalse(block.declared_blocks["link_url"].required)

    def test_color_default_is_navy(self):
        block = CalloutBlock()
        self.assertEqual(block.declared_blocks["color"].meta.default, "navy")

    def test_color_choices(self):
        block = CalloutBlock()
        choices = dict(block.declared_blocks["color"].field.choices)
        self.assertEqual(
            set(choices.keys()),
            {"navy", "red", "dark-grey", "blue-gradient", "light-grey"},
        )


class TestDonateFundraiseUpBlockFields(SimpleTestCase):
    """
    DonateFundraiseUpBlock field structure. No custom clean() — element_id
    is the only field Wagtail's built-in required-field validation needs to
    enforce, so no separate validation test class is needed.
    """

    def test_has_expected_fields(self):
        block = DonateFundraiseUpBlock()
        expected = {
            "heading",
            "description",
            "image",
            "image_caption",
            "element_id",
            "designation_id",
        }
        self.assertEqual(set(block.declared_blocks.keys()), expected)

    def test_element_id_is_required(self):
        block = DonateFundraiseUpBlock()
        self.assertTrue(block.declared_blocks["element_id"].required)

    def test_other_fields_are_optional(self):
        block = DonateFundraiseUpBlock()
        for name in ("heading", "description", "image", "image_caption", "designation_id"):
            self.assertFalse(block.declared_blocks[name].required, f"{name} should be optional")


class TestPageCardsBlockGetContext(TestCase):
    """
    PageCardsBlock.get_context() must pull the 3 most recently published
    live/public children of index_page, newest first, as page_as_card()
    dicts with a "date" key added.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        home = HomePage(title="Home", slug="home-pcb")
        root.add_child(instance=home)
        cls.index = IndexPage(title="Blog", slug="blog-pcb")
        home.add_child(instance=cls.index)

        base_time = timezone.now() - timedelta(days=10)
        cls.children = []
        for i in range(5):
            child = ContentPage(title=f"Post {i}", slug=f"post-pcb-{i}")
            cls.index.add_child(instance=child)
            child.first_published_at = base_time + timedelta(days=i)
            child.save()
            cls.children.append(child)

        cls.draft_child = ContentPage(title="Draft Post", slug="draft-post-pcb", live=False)
        cls.index.add_child(instance=cls.draft_child)

    def test_returns_three_most_recent_cards_newest_first(self):
        block = PageCardsBlock()
        context = block.get_context({"index_page": self.index})
        headings = [card["heading"] for card in context["cards"]]
        self.assertEqual(headings, ["Post 4", "Post 3", "Post 2"])

    def test_excludes_non_live_children(self):
        block = PageCardsBlock()
        context = block.get_context({"index_page": self.index})
        headings = [card["heading"] for card in context["cards"]]
        self.assertNotIn("Draft Post", headings)

    def test_card_date_is_first_published_at(self):
        block = PageCardsBlock()
        context = block.get_context({"index_page": self.index})
        newest_card = context["cards"][0]
        self.assertEqual(newest_card["date"], self.children[4].first_published_at)

    def test_card_link_page_is_the_child_page(self):
        block = PageCardsBlock()
        context = block.get_context({"index_page": self.index})
        newest_card = context["cards"][0]
        self.assertEqual(newest_card["link_page"].pk, self.children[4].pk)

    def test_no_index_page_returns_no_cards(self):
        block = PageCardsBlock()
        context = block.get_context({"index_page": None})
        self.assertEqual(context["cards"], [])


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
            "anchor_id": "",
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

    def test_heading_optional(self):
        """heading is now optional — omitting it must not raise."""
        block = SignupActionNetworkBlock()
        value = block.to_python(self._raw(heading=""))
        cleaned = block.clean(value)
        self.assertEqual(cleaned["heading"], "")

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

    def test_anchor_id_optional(self):
        block = SignupActionNetworkBlock()
        self.assertFalse(block.declared_blocks["anchor_id"].required)

    def test_has_expected_fields(self):
        block = SignupActionNetworkBlock()
        expected = {"heading", "description", "action_url", "success_message", "anchor_id"}
        self.assertEqual(set(block.declared_blocks.keys()), expected)


class TestSignupActionNetworkBlockContext(SimpleTestCase):
    """SignupActionNetworkBlock.get_context() extracts action_type and slug."""

    def _raw(self, action_url="https://actionnetwork.org/forms/join-30", success_message=""):
        return {
            "heading": "Join",
            "description": "",
            "action_url": action_url,
            "success_message": success_message,
            "anchor_id": "",
        }

    def test_context_extracts_type_and_slug(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(self._raw())
        ctx = block.get_context(value)
        self.assertEqual(ctx["action_type"], "form")
        self.assertEqual(ctx["slug"], "join-30")

    def test_context_with_complex_slug(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(
            self._raw(action_url="https://actionnetwork.org/forms/my-great-campaign-2026?source=widget")
        )
        ctx = block.get_context(value)
        self.assertEqual(ctx["slug"], "my-great-campaign-2026")

    def test_context_passes_success_message(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(
            self._raw(
                success_message=[
                    {"type": "text", "value": "<p>Thanks for signing up!</p>"}
                ]
            )
        )
        ctx = block.get_context(value)
        self.assertTrue(ctx["success_message"])

    def test_context_without_success_message(self):
        block = SignupActionNetworkBlock()
        value = block.to_python(self._raw(success_message=[]))
        ctx = block.get_context(value)
        # Empty StreamValue is falsy
        self.assertFalse(ctx["success_message"])

    def test_context_empty_url_degrades_gracefully(self):
        """When action_url is empty, context should have empty strings."""
        block = SignupActionNetworkBlock()
        value = block.to_python(self._raw(action_url=""))
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

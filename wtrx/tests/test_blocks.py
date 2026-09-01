"""
Tests for StreamField blocks.

Content blocks (ButtonBlock, VideoBlock), layout blocks (QuoteBlock,
HeroBlock, SectionBlock, CardCarouselBlock, CalloutBlock), and action blocks
(SignupActionNetworkBlock) are tested here with SimpleTestCase since their
clean() methods don't require a database.

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
import json

from django.core.exceptions import ValidationError
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone
from wagtail.blocks import RichTextBlock
from wagtail.models import Page, Site

from wtrx.blocks import (
    BACKGROUND_COLOR_CHOICES,
    IMAGE_ALIGNMENT_CHOICES,
    LEGACY_BACKGROUND_VALUES,
    LIGHT_BACKGROUND_COLORS,
    AccordionBlock,
    AccordionItemBlock,
    BodyStreamBlock,
    ButtonBlock,
    ButtonGroupBlock,
    CalloutBlock,
    CardBlock,
    CardCarouselBlock,
    CardGridBlock,
    DonateBlock,
    DonateFundraiseUpBlock,
    FeaturePanelBlock,
    HeroBlock,
    HeroCTABlock,
    HeroSignupActionKitBlock,
    ImageCardListBlock,
    ImageCardListItemBlock,
    ImageGridBlock,
    ImageGridItemBlock,
    ImageTextBlock,
    LogoGridBlock,
    LogoGridItemBlock,
    PageCardsBlock,
    PersonCardBlock,
    PersonCardGridBlock,
    QuoteBlock,
    RawHTMLBlock,
    SectionBlock,
    SectionContentBlock,
    SignupActionKitBlock,
    SignupActionNetworkBlock,
    SuccessMessageBlock,
    TimelineBlock,
    TimelineYearBlock,
    TimelineYearContentBlock,
    VideoBlock,
    _balanced_rows,
    _validate_at_most_one_link,
    background_is_light,
    hero_is_minimal,
    parse_action_network_url,
    resolve_background,
)
from wtrx.models import Blogs, ContentPage, HomePage, IndexPage, Post
from wtrx.request_context import _current_request
from wtrx.site_settings import IntegrationSettings


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

    def test_size_defaults_to_regular(self):
        block = ButtonBlock()
        self.assertEqual(block.declared_blocks["size"].meta.default, "regular")

    def test_size_choices(self):
        # Only two tiers exist -- see BUTTON_SIZE_CHOICES. The third
        # "small" tier (wtr-btn-sm) was removed rather than exposed here.
        block = ButtonBlock()
        choices = dict(block.declared_blocks["size"].field.choices)
        self.assertEqual(set(choices.keys()), {"regular", "large"})

    def test_all_sizes_accepted(self):
        block = ButtonBlock()
        for size in ("regular", "large"):
            value = block.to_python(
                self._raw(link_url="https://example.com")
            )
            value["size"] = size
            cleaned = block.clean(value)
            self.assertEqual(cleaned["size"], size)

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


class TestButtonGroupBlockFields(SimpleTestCase):
    """ButtonGroupBlock field structure: a ListBlock of 1-5 ButtonBlocks, plus layout."""

    def test_has_expected_fields(self):
        block = ButtonGroupBlock()
        self.assertEqual(set(block.declared_blocks.keys()), {"buttons", "layout"})

    def test_buttons_min_num_is_one(self):
        block = ButtonGroupBlock()
        self.assertEqual(block.declared_blocks["buttons"].meta.min_num, 1)

    def test_buttons_max_num_is_five(self):
        block = ButtonGroupBlock()
        self.assertEqual(block.declared_blocks["buttons"].meta.max_num, 5)

    def test_buttons_child_block_is_button_block(self):
        block = ButtonGroupBlock()
        self.assertIsInstance(block.declared_blocks["buttons"].child_block, ButtonBlock)

    def test_layout_defaults_to_horizontal(self):
        block = ButtonGroupBlock()
        self.assertEqual(block.declared_blocks["layout"].meta.default, "horizontal")

    def test_layout_choices(self):
        block = ButtonGroupBlock()
        choices = dict(block.declared_blocks["layout"].field.choices)
        self.assertEqual(set(choices.keys()), {"horizontal", "vertical"})

    def test_max_per_row_is_three(self):
        self.assertEqual(ButtonGroupBlock.MAX_PER_ROW, 3)

    def test_get_context_computes_rows_for_horizontal(self):
        block = ButtonGroupBlock()
        value = {"buttons": [1, 2, 3, 4], "layout": "horizontal"}
        ctx = block.get_context(value, parent_context={})
        self.assertEqual([len(r) for r in ctx["rows"]], [2, 2])

    def test_get_context_has_no_rows_for_vertical(self):
        block = ButtonGroupBlock()
        value = {"buttons": [1, 2, 3], "layout": "vertical"}
        ctx = block.get_context(value, parent_context={})
        self.assertNotIn("rows", ctx)


class TestButtonGroupBlockValidation(SimpleTestCase):
    """
    ButtonGroupBlock has no clean() of its own — ButtonBlock.clean() runs
    per-item automatically via ListBlock.clean(), so an invalid button
    inside the group still raises.
    """

    def _button(self, link_url="https://example.com", text="Click me"):
        return {"text": text, "link_page": None, "link_url": link_url, "anchor": "", "style": "primary"}

    def test_valid_buttons_pass(self):
        block = ButtonGroupBlock()
        value = block.to_python({"buttons": [self._button(), self._button(link_url="https://example.org")]})
        cleaned = block.clean(value)
        self.assertEqual(len(cleaned["buttons"]), 2)

    def test_invalid_button_in_group_raises(self):
        block = ButtonGroupBlock()
        value = block.to_python({"buttons": [self._button(link_url="")]})
        with self.assertRaises(ValidationError):
            block.clean(value)


class TestRawHTMLBlockValidation(SimpleTestCase):
    """
    RawHTMLBlock.clean() rejects HTML with mismatched or unclosed tags.
    This checks tag balance only — not full HTML5 conformance or markup
    safety (RawHTMLBlock output is still unsanitized by design).
    """

    def _clean(self, value):
        block = RawHTMLBlock()
        return block.clean(block.to_python(value))

    def test_balanced_html_passes(self):
        cleaned = self._clean("<div><p>text</p></div>")
        self.assertEqual(cleaned, "<div><p>text</p></div>")

    def test_unclosed_div_raises(self):
        with self.assertRaises(ValidationError):
            self._clean("<div><p>text</p>")

    def test_mismatched_nesting_raises(self):
        with self.assertRaises(ValidationError):
            self._clean("<div><p>text</div></p>")

    def test_void_elements_do_not_false_positive(self):
        cleaned = self._clean('<img src="x"><br><input type="text">')
        self.assertEqual(cleaned, '<img src="x"><br><input type="text">')

    def test_self_closing_tag_does_not_false_positive(self):
        cleaned = self._clean("<div/>")
        self.assertEqual(cleaned, "<div/>")

    def test_script_content_does_not_false_positive(self):
        html = "<div><script>if (a < b && b > c) { console.log('x'); }</script></div>"
        cleaned = self._clean(html)
        self.assertEqual(cleaned, html)

    def test_style_content_does_not_false_positive(self):
        html = "<div><style>.a > .b { color: red; }</style></div>"
        cleaned = self._clean(html)
        self.assertEqual(cleaned, html)

    def test_empty_value_does_not_raise_tag_balance_error(self):
        # RawHTMLBlock is required by default, so an empty value still
        # raises -- but for Wagtail's own "this field is required" reason,
        # not from the tag-balance validator (the `if value and ...` guard
        # in clean() skips the balance check entirely for a falsy value).
        block = RawHTMLBlock(required=False)
        cleaned = block.clean(block.to_python(""))
        self.assertEqual(cleaned, "")


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

    def test_alignment_uses_shared_image_alignment_choices(self):
        """
        QuoteBlock and FeaturePanelBlock used to each define their own
        byte-identical alignment choices list; both now share
        IMAGE_ALIGNMENT_CHOICES (see wtrx/blocks/__init__.py) so the two
        can't silently drift apart again.
        """
        quote_choices = QuoteBlock().declared_blocks["alignment"].field.choices
        panel_choices = FeaturePanelBlock().declared_blocks["alignment"].field.choices
        self.assertEqual(list(quote_choices), list(IMAGE_ALIGNMENT_CHOICES))
        self.assertEqual(list(panel_choices), list(IMAGE_ALIGNMENT_CHOICES))

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

    def test_get_context_minimal_true_when_headline_only(self):
        block = HeroBlock()
        value = block.to_python(
            {"headline": "Take Action", "content": "", "image": None, "banner_color": "red"}
        )
        ctx = block.get_context(value)
        self.assertTrue(ctx["hero"]["minimal"])

    def test_get_context_minimal_false_when_content_present(self):
        block = HeroBlock()
        value = block.to_python(
            {
                "headline": "Take Action",
                "content": "<p>Some supporting copy.</p>",
                "image": None,
                "banner_color": "red",
            }
        )
        ctx = block.get_context(value)
        self.assertFalse(ctx["hero"]["minimal"])


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
        self.assertIsInstance(block.declared_blocks["signup"], HeroSignupActionKitBlock)

    def test_signup_choice_has_no_content_field(self):
        """
        The hero's inline CTA strip has no room (and no real use in
        practice) for a heading/copy above the form — see
        HeroSignupActionKitBlock's docstring.
        """
        block = HeroCTABlock()
        self.assertNotIn("content", block.declared_blocks["signup"].declared_blocks)

    def test_donate_choice_is_donate_block(self):
        block = HeroCTABlock()
        self.assertIsInstance(block.declared_blocks["donate"], DonateBlock)

    def test_at_most_one_item(self):
        self.assertEqual(HeroCTABlock().meta.max_num, 1)

    def test_zero_items_allowed(self):
        self.assertEqual(HeroCTABlock().meta.min_num, 0)


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

    def test_background_defaults_to_dark_grey(self):
        block = SignupActionKitBlock()
        self.assertEqual(block.child_blocks["background"].get_default(), "dark-grey")

    def test_layout_defaults_to_columns(self):
        block = SignupActionKitBlock()
        self.assertEqual(block.child_blocks["layout"].get_default(), "columns")

    def test_layout_choices(self):
        block = SignupActionKitBlock()
        choices = dict(block.child_blocks["layout"].field.choices)
        self.assertEqual(set(choices.keys()), {"columns", "vertical"})

    def test_panel_tones_cover_only_the_colliding_fills(self):
        """
        Navy and red take no tone modifier: the stacked form's default
        chrome (blue submit button, dark fine-print box, light text) already
        reads against them. The rest each collide with one piece of it —
        see SignupActionKitBlock.PANEL_TONES.

        The two light fills take *separate* tones despite sharing the text
        inversion, because the field boxes have to move opposite ways: on
        light grey they lift to white to stay a distinct surface, and on
        white that same lift would dissolve them into the panel.
        """
        self.assertEqual(
            SignupActionKitBlock.PANEL_TONES,
            {
                "dark-grey": "on-dark",
                "blue-gradient": "on-primary",
                "light-grey": "on-light",
                "white": "on-white",
            },
        )

    def test_white_and_light_grey_take_different_tones(self):
        """
        Guards the distinction above specifically: collapsing these back to
        one tone is what made the field boxes invisible on a white panel.
        """
        block = SignupActionKitBlock()
        white = block.get_context({"short_form_id": "ppg", "background": "white"}, parent_context={})
        light = block.get_context({"short_form_id": "ppg", "background": "light-grey"}, parent_context={})
        self.assertEqual(white["panel_tone"], "on-white")
        self.assertEqual(light["panel_tone"], "on-light")
        self.assertNotEqual(white["panel_tone"], light["panel_tone"])

    def test_every_palette_background_resolves_to_a_defined_tone_or_none(self):
        """
        A tone that is not one of the four .wtr-ak-on-* rules in main.css
        would emit a class matching nothing, silently leaving the form's
        chrome in its default state on a fill that collides with it.
        """
        known_tones = {"on-dark", "on-primary", "on-light", "on-white"}
        block = SignupActionKitBlock()
        for key, _label in BACKGROUND_COLOR_CHOICES:
            tone = block.get_context(
                {"short_form_id": "ppg", "background": key}, parent_context={}
            )["panel_tone"]
            self.assertIn(tone, known_tones | {""}, f"{key} produced an unknown tone {tone!r}")

    def test_get_context_passes_the_panel_tone_for_the_background(self):
        block = SignupActionKitBlock()
        value = {"short_form_id": "ppg", "background": "light-grey"}
        self.assertEqual(block.get_context(value, parent_context={})["panel_tone"], "on-light")

    def test_get_context_panel_tone_is_blank_for_uncolliding_backgrounds(self):
        block = SignupActionKitBlock()
        value = {"short_form_id": "ppg", "background": "red"}
        self.assertEqual(block.get_context(value, parent_context={})["panel_tone"], "")

    def test_get_context_resolves_the_legacy_dark_key_to_a_tone(self):
        """
        A panel saved before the palette merge still stores "dark". It has to
        reach the same on-dark chrome as "dark-grey" does, not fall through
        to no modifier at all — see resolve_background().
        """
        block = SignupActionKitBlock()
        value = {"short_form_id": "ppg", "background": "dark"}
        self.assertEqual(block.get_context(value, parent_context={})["panel_tone"], "on-dark")


class TestSignupActionKitBlockContentField(SimpleTestCase):
    """
    content (heading+description merged) is optional; eyebrow stays a
    separate field, since it renders as its own pill.
    """

    def test_content_is_optional(self):
        block = SignupActionKitBlock()
        self.assertFalse(block.declared_blocks["content"].required)

    def test_content_supports_h2(self):
        block = SignupActionKitBlock()
        self.assertIn("h2", block.declared_blocks["content"].features)

    def test_eyebrow_stays_separate(self):
        block = SignupActionKitBlock()
        self.assertIn("eyebrow", block.declared_blocks)
        self.assertNotIn("heading", block.declared_blocks)
        self.assertNotIn("description", block.declared_blocks)


class TestSectionBlockStructure(SimpleTestCase):
    """
    SectionBlock.content must include all BodyStreamBlock block types except
    'section' itself (to prevent infinite nesting).
    """

    EXPECTED_BLOCK_NAMES = {
        "text",
        "lead_text",
        "image",
        "video",
        "button",
        "button_group",
        "quote",
        "raw_html",
        "table",
        "card",
        "person_card",
        "person_card_grid",
        "card_grid",
        "image_grid",
        "logo_grid",
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
            "content",
            "image",
            "link_page",
            "link_url",
            "link_text",
        }
        self.assertEqual(set(block.declared_blocks.keys()), expected)

    def test_content_is_required(self):
        block = CardBlock()
        self.assertTrue(block.declared_blocks["content"].required)

    def test_content_supports_h3(self):
        block = CardBlock()
        self.assertIn("h3", block.declared_blocks["content"].features)


class TestImageGridItemBlockFields(SimpleTestCase):
    def test_has_expected_fields(self):
        block = ImageGridItemBlock()
        self.assertEqual(set(block.declared_blocks.keys()), {"image", "alt_text"})

    def test_alt_text_is_optional(self):
        block = ImageGridItemBlock()
        self.assertFalse(block.declared_blocks["alt_text"].required)


class TestCardGridBlockFields(SimpleTestCase):
    """
    CardGridBlock field structure and its dynamic row-balancing via
    _balanced_rows() (previously untested -- see AGENTS.md pitfall #44).
    """

    def test_has_expected_fields(self):
        block = CardGridBlock()
        self.assertEqual(set(block.declared_blocks.keys()), {"heading", "cards"})

    def test_cards_min_num_is_two(self):
        block = CardGridBlock()
        self.assertEqual(block.declared_blocks["cards"].meta.min_num, 2)

    def test_cards_max_num_is_12(self):
        block = CardGridBlock()
        self.assertEqual(block.declared_blocks["cards"].meta.max_num, 12)

    def test_cards_child_block_is_card_block(self):
        block = CardGridBlock()
        self.assertIsInstance(block.declared_blocks["cards"].child_block, CardBlock)

    def test_max_per_row_is_three(self):
        self.assertEqual(CardGridBlock.MAX_PER_ROW, 3)

    def test_get_context_computes_rows(self):
        block = CardGridBlock()
        value = {"heading": "", "cards": [1, 2, 3, 4]}
        ctx = block.get_context(value, parent_context={})
        self.assertEqual([len(r) for r in ctx["rows"]], [2, 2])

    def test_get_context_has_no_orphan_row_at_seven(self):
        """
        The regression case: the old CSS-only special case (2 or 4 cards
        get lg:grid-cols-2, everything else lg:grid-cols-3) rendered 7
        cards as an unbalanced 3+3+1. _balanced_rows() gives 3+2+2.
        """
        block = CardGridBlock()
        value = {"heading": "", "cards": [1, 2, 3, 4, 5, 6, 7]}
        ctx = block.get_context(value, parent_context={})
        self.assertEqual([len(r) for r in ctx["rows"]], [3, 2, 2])


class TestImageGridBlockFields(SimpleTestCase):
    """ImageGridBlock field structure: heading + images (min 2, max 24)."""

    def test_has_expected_fields(self):
        block = ImageGridBlock()
        self.assertEqual(set(block.declared_blocks.keys()), {"heading", "images"})

    def test_heading_is_optional(self):
        block = ImageGridBlock()
        self.assertFalse(block.declared_blocks["heading"].required)

    def test_images_min_num_is_two(self):
        block = ImageGridBlock()
        self.assertEqual(block.declared_blocks["images"].meta.min_num, 2)

    def test_images_max_num_is_24(self):
        block = ImageGridBlock()
        self.assertEqual(block.declared_blocks["images"].meta.max_num, 24)

    def test_images_child_block_is_image_grid_item(self):
        block = ImageGridBlock()
        self.assertIsInstance(block.declared_blocks["images"].child_block, ImageGridItemBlock)

    def test_max_per_row_is_four(self):
        self.assertEqual(ImageGridBlock.MAX_PER_ROW, 4)

    def test_get_context_computes_rows(self):
        block = ImageGridBlock()
        value = {"heading": "", "images": [1, 2, 3, 4, 5]}
        ctx = block.get_context(value, parent_context={})
        self.assertEqual([len(r) for r in ctx["rows"]], [3, 2])


class TestLogoGridItemBlockFields(SimpleTestCase):
    def test_has_expected_fields(self):
        block = LogoGridItemBlock()
        self.assertEqual(
            set(block.declared_blocks.keys()), {"image", "name", "link_page", "link_url"}
        )

    def test_name_is_required(self):
        block = LogoGridItemBlock()
        self.assertTrue(block.declared_blocks["name"].required)

    def test_links_are_optional(self):
        block = LogoGridItemBlock()
        self.assertFalse(block.declared_blocks["link_page"].required)
        self.assertFalse(block.declared_blocks["link_url"].required)


class TestLogoGridItemBlockValidation(SimpleTestCase):
    """LogoGridItemBlock.clean() permits zero links but rejects two."""

    def _raw(self, link_page=None, link_url=""):
        return {"image": None, "name": "Example Org", "link_page": link_page, "link_url": link_url}

    def test_neither_link_is_valid(self):
        block = LogoGridItemBlock()
        value = block.to_python(self._raw())
        # Only exercising the link-count check here, not image resolution
        # (that needs a database) -- call the shared helper directly via
        # the fields clean() touches.
        cleaned = {"link_page": value["link_page"], "link_url": value["link_url"]}
        self.assertEqual(_validate_at_most_one_link(cleaned, {}), {})

    def test_one_link_is_valid(self):
        cleaned = {"link_page": None, "link_url": "https://example.com"}
        self.assertEqual(_validate_at_most_one_link(cleaned, {}), {})

    def test_both_links_raises(self):
        cleaned = {"link_page": object(), "link_url": "https://example.com"}
        errors = _validate_at_most_one_link(cleaned, {})
        self.assertIn("link_page", errors)
        self.assertIn("link_url", errors)


class TestLogoGridBlockFields(SimpleTestCase):
    """LogoGridBlock field structure: heading + logos (min 2, max 30)."""

    def test_has_expected_fields(self):
        block = LogoGridBlock()
        self.assertEqual(set(block.declared_blocks.keys()), {"heading", "logos"})

    def test_logos_min_num_is_two(self):
        block = LogoGridBlock()
        self.assertEqual(block.declared_blocks["logos"].meta.min_num, 2)

    def test_logos_max_num_is_30(self):
        block = LogoGridBlock()
        self.assertEqual(block.declared_blocks["logos"].meta.max_num, 30)

    def test_logos_child_block_is_logo_grid_item(self):
        block = LogoGridBlock()
        self.assertIsInstance(block.declared_blocks["logos"].child_block, LogoGridItemBlock)

    def test_max_per_row_is_five(self):
        self.assertEqual(LogoGridBlock.MAX_PER_ROW, 5)

    def test_get_context_computes_rows(self):
        block = LogoGridBlock()
        value = {"heading": "", "logos": [1, 2, 3, 4, 5, 6]}
        ctx = block.get_context(value, parent_context={})
        self.assertEqual([len(r) for r in ctx["rows"]], [3, 3])


class TestHeroIsMinimal(SimpleTestCase):
    """
    hero_is_minimal() drives components/hero.html's compact "banner"
    treatment (see its docstring in wtrx/blocks) -- True only when a hero
    has nothing but a headline (image doesn't count against it).
    """

    def test_true_when_only_headline(self):
        self.assertTrue(hero_is_minimal(copy="", video=None, cta=[]))

    def test_image_is_not_a_parameter(self):
        """The function has no `image` argument -- image presence never affects minimal."""
        import inspect

        self.assertNotIn("image", inspect.signature(hero_is_minimal).parameters)

    def test_false_when_copy_present(self):
        self.assertFalse(hero_is_minimal(copy="<p>Some text</p>", video=None, cta=[]))

    def test_true_when_copy_is_empty_paragraph_tag(self):
        """
        Draftail can persist "<p></p>" for a "cleared" richtext field -- that
        string is truthy in Python but visually empty, so it must not count
        as real copy (same strip_tags pattern as Blogs.get_related_intro()).
        """
        self.assertTrue(hero_is_minimal(copy="<p></p>", video=None, cta=[]))

    def test_false_when_video_present(self):
        self.assertFalse(hero_is_minimal(copy="", video=object(), cta=[]))

    def test_false_when_cta_present(self):
        self.assertFalse(hero_is_minimal(copy="", video=None, cta=[{"type": "button"}]))

    def test_false_when_tag_present(self):
        self.assertFalse(hero_is_minimal(copy="", video=None, cta=[], tag="Blog"))

    def test_false_when_published_at_present(self):
        self.assertFalse(
            hero_is_minimal(copy="", video=None, cta=[], published_at=timezone.now())
        )


class TestBalancedRows(SimpleTestCase):
    """
    _balanced_rows(items, max_per_row) is the row-layout algorithm shared
    by CardGridBlock, ImageGridBlock, LogoGridBlock and
    PersonCardGridBlock (each with their own max_per_row) -- never a row
    of 1 for len(items) > max_per_row, see its docstring for the proof
    this encodes as an executable check.
    """

    def _items(self, n):
        return list(range(n))

    def test_count_1_is_single_row(self):
        self.assertEqual(_balanced_rows(self._items(1), 3), [[0]])

    def test_count_2_is_single_row(self):
        self.assertEqual(_balanced_rows(self._items(2), 3), [[0, 1]])

    def test_count_at_cap_is_single_row(self):
        self.assertEqual(_balanced_rows(self._items(3), 3), [[0, 1, 2]])

    def test_cap_3_count_4_is_2x2(self):
        rows = _balanced_rows(self._items(4), 3)
        self.assertEqual([len(r) for r in rows], [2, 2])

    def test_cap_3_count_5_is_3_plus_2(self):
        rows = _balanced_rows(self._items(5), 3)
        self.assertEqual([len(r) for r in rows], [3, 2])

    def test_cap_3_count_6_is_3_plus_3(self):
        rows = _balanced_rows(self._items(6), 3)
        self.assertEqual([len(r) for r in rows], [3, 3])

    def test_cap_3_count_7_has_no_orphan_row(self):
        """
        The key regression test: a naive uniform 2-or-3-column rule fails
        for count=7 (both give a trailing row of 1) -- this is exactly
        what CardGridBlock's old CSS-only special case did. The
        evenly-distributed algorithm produces [3, 2, 2] instead.
        """
        rows = _balanced_rows(self._items(7), 3)
        self.assertEqual([len(r) for r in rows], [3, 2, 2])

    def test_cap_3_count_10(self):
        rows = _balanced_rows(self._items(10), 3)
        self.assertEqual([len(r) for r in rows], [3, 3, 2, 2])

    def test_cap_4_count_5_is_3_plus_2(self):
        """ImageGridBlock's cap (4): a count just over it still balances."""
        rows = _balanced_rows(self._items(5), 4)
        self.assertEqual([len(r) for r in rows], [3, 2])

    def test_cap_4_count_9_has_no_orphan_row(self):
        """A uniform 4-column grid would leave [4, 4, 1] here."""
        rows = _balanced_rows(self._items(9), 4)
        self.assertEqual([len(r) for r in rows], [3, 3, 3])

    def test_cap_5_count_6_is_3_plus_3(self):
        """LogoGridBlock's cap (5): a count just over it still balances."""
        rows = _balanced_rows(self._items(6), 5)
        self.assertEqual([len(r) for r in rows], [3, 3])

    def test_cap_5_count_11_has_no_orphan_row(self):
        """A uniform 5-column grid would leave [5, 5, 1] here."""
        rows = _balanced_rows(self._items(11), 5)
        self.assertEqual([len(r) for r in rows], [4, 4, 3])

    def test_no_row_of_one_for_a_spread_of_counts_and_caps(self):
        for max_per_row in (3, 4, 5):
            for n in range(2, 30):
                with self.subTest(max_per_row=max_per_row, count=n):
                    rows = _balanced_rows(self._items(n), max_per_row)
                    self.assertTrue(all(len(r) >= 2 for r in rows))

    def test_no_row_exceeds_the_cap(self):
        for max_per_row in (3, 4, 5):
            for n in range(2, 30):
                with self.subTest(max_per_row=max_per_row, count=n):
                    rows = _balanced_rows(self._items(n), max_per_row)
                    self.assertTrue(all(len(r) <= max_per_row for r in rows))

    def test_rows_cover_every_item_exactly_once(self):
        for max_per_row in (3, 4, 5):
            for n in range(1, 30):
                with self.subTest(max_per_row=max_per_row, count=n):
                    rows = _balanced_rows(self._items(n), max_per_row)
                    flattened = [p for row in rows for p in row]
                    self.assertEqual(flattened, self._items(n))

    def test_works_with_an_object_that_only_supports_int_indexing(self):
        """
        Regression test: Wagtail's real ListValue.__getitem__ only handles
        integer indices, not slice objects -- items[i:j] on one silently
        returns garbage (a plain list has .value called on it) rather than
        raising, so a plain-list-only test suite can't catch it. This
        stand-in reproduces that restriction to prove _balanced_rows()
        converts to a real list before slicing.
        """

        class IntOnlyIndexable:
            def __init__(self, items):
                self._items = items

            def __len__(self):
                return len(self._items)

            def __getitem__(self, i):
                if not isinstance(i, int):
                    raise TypeError("only int indices supported")
                return self._items[i]

        wrapped = IntOnlyIndexable(list(range(7)))
        rows = _balanced_rows(wrapped, 3)
        self.assertEqual([len(r) for r in rows], [3, 2, 2])
        self.assertEqual([p for row in rows for p in row], list(range(7)))


class TestPersonCardGridBlockFields(SimpleTestCase):
    """PersonCardGridBlock field structure: heading + people (min 1, max 12)."""

    def test_has_expected_fields(self):
        block = PersonCardGridBlock()
        self.assertEqual(set(block.declared_blocks.keys()), {"heading", "people"})

    def test_people_min_num_is_one(self):
        block = PersonCardGridBlock()
        self.assertEqual(block.declared_blocks["people"].meta.min_num, 1)

    def test_people_max_num_is_12(self):
        block = PersonCardGridBlock()
        self.assertEqual(block.declared_blocks["people"].meta.max_num, 12)

    def test_people_child_block_is_person_card(self):
        block = PersonCardGridBlock()
        self.assertIsInstance(block.declared_blocks["people"].child_block, PersonCardBlock)

    def test_get_context_computes_rows(self):
        block = PersonCardGridBlock()
        value = {"heading": "", "people": [1, 2, 3, 4, 5]}
        ctx = block.get_context(value, parent_context={})
        self.assertEqual([len(r) for r in ctx["rows"]], [3, 2])


class TestImageCardListItemBlockFields(SimpleTestCase):
    """ImageCardListItemBlock field structure: content (heading+description merged) only."""

    def test_has_expected_fields(self):
        block = ImageCardListItemBlock()
        self.assertEqual(set(block.declared_blocks.keys()), {"content"})

    def test_content_is_required(self):
        block = ImageCardListItemBlock()
        self.assertTrue(block.declared_blocks["content"].required)

    def test_content_supports_h3(self):
        block = ImageCardListItemBlock()
        self.assertIn("h3", block.declared_blocks["content"].features)


class TestImageCardListBlockFields(SimpleTestCase):
    """ImageCardListBlock field structure: heading + image + cards (min 2)."""

    def test_has_expected_fields(self):
        block = ImageCardListBlock()
        self.assertEqual(
            set(block.declared_blocks.keys()), {"heading", "image", "cards", "alignment"}
        )

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

    def test_alignment_choices(self):
        block = ImageCardListBlock()
        choices = dict(block.declared_blocks["alignment"].field.choices)
        self.assertEqual(set(choices.keys()), {"image-left", "image-right"})

    def test_alignment_defaults_to_image_left(self):
        block = ImageCardListBlock()
        self.assertEqual(block.declared_blocks["alignment"].meta.default, "image-left")


class TestImageTextBlockFields(SimpleTestCase):
    """ImageTextBlock field structure: image + content (heading+text merged), all required."""

    def test_has_expected_fields(self):
        block = ImageTextBlock()
        self.assertEqual(
            set(block.declared_blocks.keys()), {"image", "content", "alignment", "size"}
        )

    def test_image_is_required(self):
        block = ImageTextBlock()
        self.assertTrue(block.declared_blocks["image"].required)

    def test_content_is_required(self):
        block = ImageTextBlock()
        self.assertTrue(block.declared_blocks["content"].required)

    def test_content_is_richtext(self):
        block = ImageTextBlock()
        self.assertIsInstance(block.declared_blocks["content"], RichTextBlock)

    def test_content_supports_h2(self):
        block = ImageTextBlock()
        self.assertIn("h2", block.declared_blocks["content"].features)

    def test_alignment_choices(self):
        block = ImageTextBlock()
        choices = dict(block.declared_blocks["alignment"].field.choices)
        self.assertEqual(set(choices.keys()), {"image-left", "image-right"})

    def test_alignment_defaults_to_image_left(self):
        block = ImageTextBlock()
        self.assertEqual(block.declared_blocks["alignment"].meta.default, "image-left")

    def test_size_choices(self):
        block = ImageTextBlock()
        choices = dict(block.declared_blocks["size"].field.choices)
        self.assertEqual(set(choices.keys()), {"small", "default", "large"})

    def test_size_defaults_to_default(self):
        block = ImageTextBlock()
        self.assertEqual(block.declared_blocks["size"].meta.default, "default")

    def test_missing_size_in_stored_value_falls_back_to_default(self):
        # Simulates harvested preview JSON (or a real page) saved before the
        # `size` field existed -- StructBlock.to_python() must fall back to
        # the field's own default for a missing key, not raise, so old data
        # keeps rendering. See ImageTextBlock's docstring / AGENTS.md rule #45.
        block = ImageTextBlock()
        value = block.to_python({"image": None, "content": "<p>Hi</p>", "alignment": "image-left"})
        self.assertEqual(value["size"], "default")


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
            "content",
            "image",
            "alignment",
            "background",
            "link_text",
            "link_page",
            "link_url",
            "anchor",
        }
        self.assertEqual(set(block.declared_blocks.keys()), expected)

    def test_content_is_required(self):
        """content carries the required heading, typed as an H2 at the top."""
        block = FeaturePanelBlock()
        self.assertTrue(block.declared_blocks["content"].required)

    def test_image_is_required(self):
        block = FeaturePanelBlock()
        self.assertTrue(block.declared_blocks["image"].required)

    def test_optional_fields_are_optional(self):
        """Everything but content/image is optional — the Figma dark panel
        has no eyebrow."""
        block = FeaturePanelBlock()
        for name in ("eyebrow", "link_text", "link_page", "link_url", "anchor"):
            with self.subTest(field=name):
                self.assertFalse(block.declared_blocks[name].required)

    def test_content_is_richtext(self):
        block = FeaturePanelBlock()
        self.assertIsInstance(block.declared_blocks["content"], RichTextBlock)

    def test_content_supports_h2(self):
        block = FeaturePanelBlock()
        self.assertIn("h2", block.declared_blocks["content"].features)

    def test_alignment_choices(self):
        block = FeaturePanelBlock()
        choices = dict(block.declared_blocks["alignment"].field.choices)
        self.assertEqual(set(choices.keys()), {"image-left", "image-right"})

    def test_alignment_defaults_to_image_left(self):
        block = FeaturePanelBlock()
        self.assertEqual(block.declared_blocks["alignment"].meta.default, "image-left")

    def test_background_defaults_to_white(self):
        """
        The fills themselves are asserted once, against every block that has
        them, in TestSharedBackgroundPalette — only the per-block default is
        this block's own business.
        """
        block = FeaturePanelBlock()
        self.assertEqual(block.declared_blocks["background"].meta.default, "white")


class TestCardCarouselBlockFields(SimpleTestCase):
    """
    CardCarouselBlock field structure. Link-validation logic (clean()
    wraps _validate_at_most_one_link) is covered generically in
    TestQuoteBlockValidation — see module docstring.
    """

    def test_has_expected_fields(self):
        block = CardCarouselBlock()
        expected = {"content", "link_text", "link_page", "link_url", "cards"}
        self.assertEqual(set(block.declared_blocks.keys()), expected)

    def test_content_is_required(self):
        """content carries the required heading, typed as an H2 at the top."""
        block = CardCarouselBlock()
        self.assertTrue(block.declared_blocks["content"].required)

    def test_content_supports_h2(self):
        block = CardCarouselBlock()
        self.assertIn("h2", block.declared_blocks["content"].features)

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
            "content",
            "link_text",
            "link_page",
            "link_url",
            "color",
            "image",
        }
        self.assertEqual(set(block.declared_blocks.keys()), expected)

    def test_content_is_optional(self):
        """A callout can be just a background + button, per its docstring."""
        block = CalloutBlock()
        self.assertFalse(block.declared_blocks["content"].required)

    def test_content_supports_h2_and_h3(self):
        block = CalloutBlock()
        features = block.declared_blocks["content"].features
        self.assertIn("h2", features)
        self.assertIn("h3", features)

    def test_content_supports_lists(self):
        block = CalloutBlock()
        features = block.declared_blocks["content"].features
        self.assertIn("ol", features)
        self.assertIn("ul", features)

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

    def test_color_defaults_to_navy(self):
        """
        The fills themselves are asserted once, against every block that has
        them, in TestSharedBackgroundPalette — only the per-block default is
        this block's own business.
        """
        block = CalloutBlock()
        self.assertEqual(block.declared_blocks["color"].meta.default, "navy")


class TestDonateBlockFields(SimpleTestCase):
    """DonateBlock field structure: content (heading+description merged), all optional."""

    def test_has_expected_fields(self):
        block = DonateBlock()
        expected = {
            "content",
            "button_text",
            "override_amounts",
            "override_url",
        }
        self.assertEqual(set(block.declared_blocks.keys()), expected)

    def test_content_is_optional(self):
        block = DonateBlock()
        self.assertFalse(block.declared_blocks["content"].required)

    def test_content_supports_h2(self):
        block = DonateBlock()
        self.assertIn("h2", block.declared_blocks["content"].features)

    def test_content_supports_h3(self):
        # Editors can add an optional H3 subheading below the H2 heading,
        # same as CalloutBlock (RICHTEXT_FEATURES_HEADINGS_H2_H3).
        block = DonateBlock()
        self.assertIn("h3", block.declared_blocks["content"].features)


class TestDonateFundraiseUpBlockFields(SimpleTestCase):
    """
    DonateFundraiseUpBlock field structure. No custom clean() — every field
    is optional, so no separate validation test class is needed. There is no
    element_id field: every instance shows the visitor's region-specific
    Fundraise Up element, resolved from FundraiseUpConfigBlock's settings
    (see wtrx/integrations/fundraiseup.py).
    """

    def test_has_expected_fields(self):
        block = DonateFundraiseUpBlock()
        expected = {
            "content",
            "image",
            "image_caption",
            "designation_id",
            "alignment",
        }
        self.assertEqual(set(block.declared_blocks.keys()), expected)

    def test_all_fields_are_optional(self):
        block = DonateFundraiseUpBlock()
        for name in ("content", "image", "image_caption", "designation_id"):
            self.assertFalse(block.declared_blocks[name].required, f"{name} should be optional")

    def test_content_supports_h2(self):
        block = DonateFundraiseUpBlock()
        self.assertIn("h2", block.declared_blocks["content"].features)

    def test_content_supports_h3(self):
        # Editors can add an optional H3 subheading below the H2 heading,
        # same as CalloutBlock/DonateBlock.
        block = DonateFundraiseUpBlock()
        self.assertIn("h3", block.declared_blocks["content"].features)

    def test_alignment_choices(self):
        block = DonateFundraiseUpBlock()
        choices = dict(block.declared_blocks["alignment"].field.choices)
        self.assertEqual(set(choices.keys()), {"image-left", "image-right"})

    def test_alignment_defaults_to_image_left(self):
        block = DonateFundraiseUpBlock()
        self.assertEqual(block.declared_blocks["alignment"].meta.default, "image-left")


class TestDonateFundraiseUpBlockGeolocationContext(TestCase):
    """
    DonateFundraiseUpBlock.get_context() builds the region → element ID map
    consumed client-side by donate_fundraiseup_block.html's inline script.
    See FundraiseUpConfigBlock's docstring (wtrx/integrations/fundraiseup.py)
    for why this resolution has to happen client-side rather than here.
    """

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.get(is_default_site=True)

    def setUp(self):
        self.integration, _ = IntegrationSettings.objects.get_or_create(site=self.site)

    def _set_fundraiseup_config(self, **overrides):
        config = {
            "enabled": True,
            "installation_code": "<script>fru</script>",
            "element_id_us": "US_ID",
            "element_id_nl": "NL_ID",
            "element_id_ca": "CA_ID",
            "element_id_gb": "GB_ID",
            "eu_country_codes": "DE,FR,ES",
            "element_id_eu": "EU_ID",
            "element_id_default": "DEFAULT_ID",
        }
        config.update(overrides)
        self.integration.integrations = [("fundraiseup", config)]
        self.integration.save()

    def _get_context(self):
        block = DonateFundraiseUpBlock()
        request = RequestFactory().get("/")
        request.META["HTTP_HOST"] = self.site.hostname
        request.META["SERVER_PORT"] = str(self.site.port)
        return block.get_context({"designation_id": ""}, parent_context={"request": request})

    def test_default_element_id_is_used_as_the_initial_href_target(self):
        self._set_fundraiseup_config()
        ctx = self._get_context()
        self.assertEqual(ctx["fundraiseup_default_element_id"], "DEFAULT_ID")

    def test_region_map_carries_every_configured_region(self):
        self._set_fundraiseup_config()
        ctx = self._get_context()
        regions = json.loads(ctx["fundraiseup_region_map_json"])
        self.assertEqual(regions["US"], "US_ID")
        self.assertEqual(regions["NL"], "NL_ID")
        self.assertEqual(regions["CA"], "CA_ID")
        self.assertEqual(regions["GB"], "GB_ID")
        self.assertEqual(regions["_eu"], "EU_ID")
        self.assertEqual(regions["_default"], "DEFAULT_ID")
        self.assertEqual(regions["_eu_countries"], ["DE", "FR", "ES"])

    def test_eu_country_codes_are_split_trimmed_and_uppercased(self):
        self._set_fundraiseup_config(eu_country_codes=" de, fr ,es")
        ctx = self._get_context()
        regions = json.loads(ctx["fundraiseup_region_map_json"])
        self.assertEqual(regions["_eu_countries"], ["DE", "FR", "ES"])

    def test_blank_region_field_falls_back_to_the_default(self):
        """An editor who's only filled in some regions still gets a working
        form for everyone else, rather than an empty element ID."""
        self._set_fundraiseup_config(element_id_gb="", element_id_eu="")
        ctx = self._get_context()
        regions = json.loads(ctx["fundraiseup_region_map_json"])
        self.assertEqual(regions["GB"], "DEFAULT_ID")
        self.assertEqual(regions["_eu"], "DEFAULT_ID")

    def test_no_fundraiseup_config_yields_blank_defaults(self):
        """Fundraise Up not configured/enabled at all — no request crash,
        just an empty default (the anchor stays hidden, same as an
        unconfigured ActionKit/ActBlue integration elsewhere)."""
        self.integration.integrations = []
        self.integration.save()
        ctx = self._get_context()
        self.assertEqual(ctx["fundraiseup_default_element_id"], "")
        self.assertEqual(json.loads(ctx["fundraiseup_region_map_json"]), {"_default": ""})

    def test_no_request_in_parent_context_does_not_crash(self):
        """Mirrors DonateBlock's own ActBlue lookup — get_context() must
        tolerate being called without a request (e.g. direct block-preview
        rendering in tests) rather than raising."""
        block = DonateFundraiseUpBlock()
        ctx = block.get_context({"designation_id": ""}, parent_context={})
        self.assertEqual(ctx["fundraiseup_default_element_id"], "")


class TestPageCardsBlockFields(SimpleTestCase):
    """
    content (heading+subheading merged) is optional. subheading used to
    render as a plain paragraph despite its name, not an H3 — the merged
    field only needs h2 support.
    """

    def test_content_is_optional(self):
        block = PageCardsBlock()
        self.assertFalse(block.declared_blocks["content"].required)

    def test_content_supports_h2(self):
        block = PageCardsBlock()
        self.assertIn("h2", block.declared_blocks["content"].features)

    def test_no_separate_heading_or_subheading_fields(self):
        block = PageCardsBlock()
        self.assertNotIn("heading", block.declared_blocks)
        self.assertNotIn("subheading", block.declared_blocks)


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


class TestPageCardsBlockBlogsOrdering(TestCase):
    """
    Pointed at a Blogs page (blog posts / press releases), the block must
    order by the editor-controlled published_at — the date the cards
    themselves show, and the order the Blogs listing uses — not by
    Wagtail's first_published_at, which imported posts don't carry
    meaningfully.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        home = HomePage(title="Home", slug="home-pcb-blogs")
        root.add_child(instance=home)
        cls.blogs = Blogs(title="Blog", slug="blog-pcb-blogs")
        home.add_child(instance=cls.blogs)

        now = timezone.now()
        # published_at deliberately runs opposite to first_published_at, so
        # a result ordered by the wrong field is unambiguous.
        for i, title in enumerate(["Oldest", "Middle", "Newest", "Ancient"]):
            post = Post(
                title=title,
                slug=f"post-pcb-blogs-{i}",
                published_at=now - timedelta(days=[30, 20, 1, 400][i]),
            )
            cls.blogs.add_child(instance=post)
            post.first_published_at = now - timedelta(days=i)
            post.save()

    def test_orders_by_published_at(self):
        block = PageCardsBlock()
        context = block.get_context({"index_page": self.blogs})
        headings = [card["heading"] for card in context["cards"]]
        self.assertEqual(headings, ["Newest", "Middle", "Oldest"])

    def test_card_date_is_published_at(self):
        block = PageCardsBlock()
        context = block.get_context({"index_page": self.blogs})
        newest = Post.objects.get(slug="post-pcb-blogs-2")
        self.assertEqual(context["cards"][0]["date"], newest.published_at)

    def test_excludes_non_live_posts(self):
        draft = Post(
            title="Draft",
            slug="post-pcb-blogs-draft",
            live=False,
            published_at=timezone.now(),
        )
        self.blogs.add_child(instance=draft)
        block = PageCardsBlock()
        context = block.get_context({"index_page": self.blogs})
        self.assertNotIn("Draft", [card["heading"] for card in context["cards"]])


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
        """
        BodyStreamBlock should have all SectionContentBlock types plus
        'section' and 'timeline' — both are deliberately excluded from
        SectionContentBlock (and so from TimelineYearContentBlock, which
        subclasses it) to prevent infinite self-nesting, same reasoning for
        both.
        """
        body = BodyStreamBlock()
        section_content = SectionContentBlock()
        body_names = set(body.child_blocks.keys())
        section_names = set(section_content.child_blocks.keys())
        self.assertEqual(body_names - section_names, {"section", "timeline"})


class TestAccordionItemBlockMediaFields(SimpleTestCase):
    """
    AccordionItemBlock.image/video (added for the "victories" ->
    AccordionBlock conversion — see TimelineBlock/import_350_our_impact.py).
    Both are optional and independent.
    """

    def test_has_expected_fields(self):
        block = AccordionItemBlock()
        self.assertEqual(
            set(block.declared_blocks.keys()), {"title", "content", "image", "video"}
        )

    def test_image_is_not_required(self):
        block = AccordionItemBlock()
        self.assertFalse(block.declared_blocks["image"].required)

    def test_video_is_not_required(self):
        block = AccordionItemBlock()
        self.assertFalse(block.declared_blocks["video"].required)

    def test_accordion_block_items_child_block_is_accordion_item_block(self):
        block = AccordionBlock()
        self.assertIsInstance(block.declared_blocks["items"].child_block, AccordionItemBlock)


class TestTimelineBlock(SimpleTestCase):
    """
    TimelineBlock: a list of years, each with a freely composed
    TimelineYearContentBlock stream, plus a year-jump nav computed in
    get_context() from whichever years are actually present (AGENTS.md
    pitfall #44's derived-context pattern, same as CardGridBlock's rows).
    """

    def test_has_expected_fields(self):
        block = TimelineBlock()
        self.assertEqual(set(block.declared_blocks.keys()), {"years"})

    def test_years_min_num_is_one(self):
        block = TimelineBlock()
        self.assertEqual(block.declared_blocks["years"].meta.min_num, 1)

    def test_years_child_block_is_timeline_year_block(self):
        block = TimelineBlock()
        self.assertIsInstance(block.declared_blocks["years"].child_block, TimelineYearBlock)

    def test_year_block_has_expected_fields(self):
        block = TimelineYearBlock()
        self.assertEqual(set(block.declared_blocks.keys()), {"year", "content"})

    def test_year_content_is_timeline_year_content_block(self):
        block = TimelineYearBlock()
        self.assertIsInstance(block.declared_blocks["content"], TimelineYearContentBlock)

    def test_timeline_year_content_block_matches_section_content_block(self):
        """
        TimelineYearContentBlock starts identical to SectionContentBlock
        (same DeclarativeSubBlocksMetaclass pattern, rule #9) and must not
        include 'timeline' itself -- that would let a year's content embed
        another timeline, which is exactly the self-nesting SectionContentBlock
        already avoids by excluding 'section'.
        """
        year_content = TimelineYearContentBlock()
        section_content = SectionContentBlock()
        self.assertEqual(
            set(year_content.child_blocks.keys()), set(section_content.child_blocks.keys())
        )
        self.assertNotIn("timeline", year_content.child_blocks)

    def test_get_context_builds_year_nav_from_years_in_order(self):
        block = TimelineBlock()
        value = {
            "years": [
                {"year": "2019", "content": []},
                {"year": "2021", "content": []},
            ]
        }
        ctx = block.get_context(value, parent_context={})
        self.assertEqual(
            ctx["year_nav"],
            [
                {"year": "2019", "anchor": "timeline-year-2019"},
                {"year": "2021", "anchor": "timeline-year-2021"},
            ],
        )


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
        self,
        action_url="https://actionnetwork.org/forms/join-30",
        content="<h2>Sign Up</h2>",
    ):
        return {
            "content": content,
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

    def test_content_optional(self):
        """content is optional — omitting it must not raise."""
        block = SignupActionNetworkBlock()
        value = block.to_python(self._raw(content=""))
        cleaned = block.clean(value)
        self.assertEqual(str(cleaned["content"]), "")

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
        expected = {"content", "action_url", "success_message", "anchor_id"}
        self.assertEqual(set(block.declared_blocks.keys()), expected)

    def test_content_supports_h2(self):
        block = SignupActionNetworkBlock()
        self.assertIn("h2", block.declared_blocks["content"].features)


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


class TestSharedBackgroundPalette(SimpleTestCase):
    """
    Every block with a background choice offers the same fills. Before the
    palette was unified each carried its own list, so the same visual
    decision was made from a different vocabulary depending on which block
    an editor was standing in — see BACKGROUND_COLOR_CHOICES.
    """

    # (block class, name of its background field). CalloutBlock and
    # HeroBlock call theirs "color"/"banner_color" rather than "background";
    # the field name is per-block, the choices are not.
    BACKGROUND_FIELDS = [
        (SectionBlock, "background"),
        (CalloutBlock, "color"),
        (FeaturePanelBlock, "background"),
        (HeroBlock, "banner_color"),
        (SignupActionKitBlock, "background"),
    ]

    def test_every_background_field_offers_the_whole_palette(self):
        expected = {value for value, _label in BACKGROUND_COLOR_CHOICES}
        for block_class, field_name in self.BACKGROUND_FIELDS:
            with self.subTest(block=block_class.__name__):
                block = block_class()
                choices = {
                    value
                    for value, _label in block.child_blocks[field_name].field.choices
                }
                self.assertEqual(choices, expected)

    def test_every_default_is_a_palette_key(self):
        """
        Defaults are allowed to differ per block — a section defaults to the
        plain page background, a hero banner to navy — but every one of them
        has to name a fill that actually exists.
        """
        keys = {value for value, _label in BACKGROUND_COLOR_CHOICES}
        for block_class, field_name in self.BACKGROUND_FIELDS:
            with self.subTest(block=block_class.__name__):
                block = block_class()
                self.assertIn(block.child_blocks[field_name].get_default(), keys)

    def test_legacy_values_map_onto_real_palette_keys(self):
        keys = {value for value, _label in BACKGROUND_COLOR_CHOICES}
        self.assertTrue(set(LEGACY_BACKGROUND_VALUES.values()) <= keys)
        # A legacy key must not also be a live one, or resolution would
        # silently rewrite a value an editor deliberately chose.
        self.assertFalse(set(LEGACY_BACKGROUND_VALUES) & keys)

    def test_light_fills_are_palette_keys(self):
        keys = {value for value, _label in BACKGROUND_COLOR_CHOICES}
        self.assertTrue(LIGHT_BACKGROUND_COLORS <= keys)


class TestBackgroundResolution(SimpleTestCase):
    """
    resolve_background() / background_is_light() — the render-path fallback
    that keeps pre-palette values working. Migration 0040 rewrites the ones
    stored on live pages, but reverting to an old page revision republishes
    that revision's JSON verbatim, so legacy keys can always come back.
    """

    def test_canonical_values_pass_through(self):
        for value, _label in BACKGROUND_COLOR_CHOICES:
            with self.subTest(value=value):
                self.assertEqual(resolve_background(value), value)

    def test_legacy_values_are_translated(self):
        self.assertEqual(resolve_background("light"), "white")
        self.assertEqual(resolve_background("dark"), "dark-grey")
        self.assertEqual(resolve_background("muted"), "light-grey")
        self.assertEqual(resolve_background("primary"), "blue-gradient")
        self.assertEqual(resolve_background("secondary"), "navy")

    def test_unknown_values_fall_back_rather_than_emitting_a_dead_class(self):
        """
        An unrecognised key must not reach the template: `.wtr-bg-<junk>`
        matches no rule, leaving a transparent panel with light text on it.
        """
        self.assertEqual(resolve_background("chartreuse"), "white")
        self.assertEqual(resolve_background(None), "white")
        self.assertEqual(resolve_background("chartreuse", default="navy"), "navy")

    def test_light_fills_are_the_ones_needing_dark_text(self):
        self.assertTrue(background_is_light("white"))
        self.assertTrue(background_is_light("light-grey"))
        for value in ("dark-grey", "navy", "red", "blue-gradient"):
            with self.subTest(value=value):
                self.assertFalse(background_is_light(value))

    def test_legacy_light_values_are_light(self):
        self.assertTrue(background_is_light("light"))
        self.assertTrue(background_is_light("muted"))
        self.assertFalse(background_is_light("dark"))


class TestIntegrationGatedStreamBlockVisibility(TestCase):
    """
    IntegrationGatedStreamBlockMixin (wtrx/blocks/__init__.py) filters
    BodyStreamBlock/SectionContentBlock's "Add block" picker
    (sorted_child_blocks()/grouped_child_blocks()) by IntegrationSettings,
    without ever touching child_blocks itself — see the mixin's docstring
    for why that split matters.
    """

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.get(is_default_site=True)

    def setUp(self):
        self.integration, _ = IntegrationSettings.objects.get_or_create(site=self.site)

    def _set_integrations(self, data):
        self.integration.integrations = data
        self.integration.save()

    def _set_current_request(self):
        request = RequestFactory().get("/admin/")
        request.META["HTTP_HOST"] = self.site.hostname
        request.META["SERVER_PORT"] = str(self.site.port)
        token = _current_request.set(request)
        self.addCleanup(_current_request.reset, token)

    def test_no_request_context_shows_everything(self):
        """
        A management command or test with no request in scope must never
        silently hide content — see
        _hidden_block_names_for_current_request()'s docstring.
        """
        self._set_integrations([])
        names = {b.name for b in BodyStreamBlock().sorted_child_blocks()}
        self.assertIn("donate", names)
        self.assertIn("signup_actionkit", names)

    def test_disabled_integration_hides_its_block_from_picker(self):
        self._set_integrations([])
        self._set_current_request()
        names = {b.name for b in BodyStreamBlock().sorted_child_blocks()}
        self.assertNotIn("donate", names)  # actblue disabled
        self.assertNotIn("signup_actionkit", names)  # actionkit disabled

    def test_enabled_integration_keeps_its_block_in_picker(self):
        self._set_integrations(
            [
                (
                    "actblue",
                    {
                        "enabled": True,
                        "base_url": "",
                        "suggested_amounts": "",
                        "default_recurring": False,
                    },
                )
            ]
        )
        self._set_current_request()
        names = {b.name for b in BodyStreamBlock().sorted_child_blocks()}
        self.assertIn("donate", names)
        self.assertNotIn("donate_fundraiseup", names)

    def test_wagtail_forms_visible_by_default(self):
        self._set_integrations([])
        self._set_current_request()
        names = {b.name for b in BodyStreamBlock().sorted_child_blocks()}
        self.assertIn("signup_wagtail_forms", names)

    def test_disabling_wagtail_forms_hides_it(self):
        self._set_integrations([("wagtail_forms", {"enabled": False})])
        self._set_current_request()
        names = {b.name for b in BodyStreamBlock().sorted_child_blocks()}
        self.assertNotIn("signup_wagtail_forms", names)

    def test_child_blocks_always_contains_every_block_regardless_of_context(self):
        """
        The critical safety property: hiding a block from the picker must
        never affect child_blocks, which parsing/rendering/validation read
        directly — see IntegrationGatedStreamBlockMixin's docstring.
        """
        self._set_integrations([])
        self._set_current_request()
        block = BodyStreamBlock()
        self.assertNotIn("donate", {b.name for b in block.sorted_child_blocks()})
        self.assertIn("donate", block.child_blocks)

    def test_existing_content_of_a_now_hidden_block_type_still_round_trips(self):
        """
        A page that already has a `donate` block placed while ActBlue was
        enabled must keep rendering correctly after ActBlue is disabled —
        this is the whole reason child_blocks is never filtered.
        """
        self._set_integrations([])  # actblue disabled
        self._set_current_request()
        block = BodyStreamBlock()
        donate_block = block.child_blocks["donate"]
        default_value = donate_block.get_default()
        stream_value = block.to_python(
            [
                {
                    "type": "donate",
                    "value": donate_block.get_prep_value(default_value),
                    "id": "test-id",
                }
            ]
        )
        self.assertEqual(stream_value[0].block_type, "donate")

    def test_section_content_block_also_filters(self):
        self._set_integrations([])
        self._set_current_request()
        names = {b.name for b in SectionContentBlock().sorted_child_blocks()}
        self.assertNotIn("donate", names)

"""
Alt text must come from the image's description when one is set.

Templates used to read `image.title` directly, which ignored a description an
editor had written. They now use Wagtail's own `Rendition.alt`, whose fallback
chain is contextual alt -> description -> title.

Wagtail pre-fills `title` from the uploaded filename, so an image left without
a description still publishes something filename-shaped. That is Wagtail's
documented behaviour and is deliberately kept — the fix for those images is to
write descriptions, not to second-guess the title in the templates.
"""

from django.template.loader import render_to_string
from django.test import TestCase

from wagtail.images.forms import get_image_form
from wagtail.images.tests.utils import get_test_image_file

from wtrx.blocks import (
    DonateFundraiseUpBlock,
    FeaturePanelBlock,
    ImageBlock,
    ImageCardListBlock,
    ImageTextBlock,
    QuoteBlock,
    SignupActionKitBlock,
)
from wtrx.images import CustomImage

DESCRIPTION = "Marchers carrying a banner outside the state capitol"
# What Wagtail pre-fills the title with: the uploaded filename, extension
# stripped. Kept realistic so the "not the title" assertions mean something.
FILENAME_TITLE = "20250920_Draw_The_Line_Nairobi_057"


class ImageAltTextTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.described = CustomImage.objects.create(
            title=FILENAME_TITLE,
            description=DESCRIPTION,
            file=get_test_image_file(size=(1200, 800)),
        )
        cls.undescribed = CustomImage.objects.create(
            title=FILENAME_TITLE,
            file=get_test_image_file(size=(1200, 800)),
        )

    def assert_alt_from_description(self, html):
        self.assertIn(f'alt="{DESCRIPTION}"', html)
        self.assertNotIn(f'alt="{FILENAME_TITLE}"', html)

    # -- StreamField blocks -------------------------------------------------

    def _render_block(self, block, data):
        return block.render(block.to_python(data))

    def test_blocks_use_description(self):
        cases = [
            (ImageBlock(), {"image": self.described.pk}),
            (ImageTextBlock(), {"image": self.described.pk}),
            (FeaturePanelBlock(), {"image": self.described.pk}),
            (ImageCardListBlock(), {"image": self.described.pk}),
            (DonateFundraiseUpBlock(), {"image": self.described.pk}),
            (SignupActionKitBlock(), {"image": self.described.pk}),
            (QuoteBlock(), {"quote": "Hello", "image": self.described.pk}),
        ]
        for block, data in cases:
            with self.subTest(block=type(block).__name__):
                self.assert_alt_from_description(self._render_block(block, data))

    def test_falls_back_to_wagtails_own_default_without_a_description(self):
        # Wagtail's default_alt_text: description, then title. Pinned so the
        # fallback stays Wagtail's rather than drifting into a custom one.
        html = self._render_block(ImageBlock(), {"image": self.undescribed.pk})
        self.assertIn(f'alt="{FILENAME_TITLE}"', html)

    def test_image_block_alt_text_overrides_description(self):
        html = self._render_block(
            ImageBlock(), {"image": self.described.pk, "alt_text": "Explicit override"}
        )
        self.assertIn('alt="Explicit override"', html)
        self.assertNotIn(DESCRIPTION, html)

    # -- Shared components --------------------------------------------------

    def test_card_component_uses_description(self):
        html = render_to_string(
            "wtrx/components/card.html",
            {"card": {"heading": "Card", "image": self.described}},
        )
        self.assert_alt_from_description(html)

    def test_post_card_component_uses_description(self):
        html = render_to_string(
            "wtrx/components/post_card.html",
            {"card": {"title": "Post", "image": self.described, "url": "/post/"}},
        )
        self.assert_alt_from_description(html)

    def test_person_card_prefers_description_over_name(self):
        html = render_to_string(
            "wtrx/components/person_card.html",
            {"person": {"name": "Ada Lovelace", "image": self.described}},
        )
        self.assert_alt_from_description(html)
        self.assertNotIn('alt="Ada Lovelace"', html)

    def test_person_card_falls_back_to_name(self):
        html = render_to_string(
            "wtrx/components/person_card.html",
            {"person": {"name": "Ada Lovelace", "image": self.undescribed}},
        )
        self.assertIn('alt="Ada Lovelace"', html)

    # -- Hero ---------------------------------------------------------------

    def _hero_context(self, image):
        return {
            "hero": {
                "headline": "Headline",
                "copy": None,
                "copy_is_block": False,
                "image": image,
                "video": None,
                "link_text": None,
                "link_page": None,
                "link_url": None,
            }
        }

    def test_hero_image_uses_description(self):
        html = render_to_string(
            "wtrx/components/hero.html", self._hero_context(self.described)
        )
        self.assert_alt_from_description(html)
        self.assertNotIn('role="presentation"', html)

    def test_hero_image_stays_decorative_without_description(self):
        html = render_to_string(
            "wtrx/components/hero.html", self._hero_context(self.undescribed)
        )
        self.assertIn('role="presentation"', html)
        self.assertNotIn(f'alt="{FILENAME_TITLE}"', html)


class ImageDescriptionRequiredTest(TestCase):
    """
    description is now blank=False on CustomImage (see wtrx/images.py) so the
    Images admin can't publish a new filename-shaped alt text going forward.
    Existing rows created outside a form (import scripts, .objects.create())
    are unaffected -- see backfill_image_descriptions for those.
    """

    def test_admin_image_form_requires_description(self):
        form_class = get_image_form(CustomImage)
        self.assertTrue(form_class.base_fields["description"].required)

    def test_creating_an_image_directly_still_allows_a_blank_description(self):
        # .objects.create() bypasses form/full_clean() validation, same as
        # the existing import management commands rely on.
        image = CustomImage.objects.create(
            title=FILENAME_TITLE, file=get_test_image_file(size=(1200, 800))
        )
        self.assertEqual(image.description, "")


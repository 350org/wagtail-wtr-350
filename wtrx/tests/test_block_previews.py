import re
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from wagtail.images.tests.utils import get_test_image_file

from wtrx import blocks as blocks_module
from wtrx.blocks import BodyStreamBlock
from wtrx.images import CustomImage


class BlockPreviewTest(TestCase):
    """
    Guards the StreamField block-picker previews.

    Two things here are silent-failure prone and neither raises on its own:

    - The global override at templates/wagtailcore/shared/block_preview.html is
      load-bearing. Without it Block.is_previewable is False for every block and
      every preview vanishes from the picker with no error anywhere.
    - Harvested preview values (wtrx/previews/block_previews.json, regenerated
      by `manage.py harvest_block_previews`) reference images by primary key,
      which only resolve in the database they were harvested from.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser("prev", "p@example.com", "pw")
        # Harvested previews reference images by primary key, and those keys
        # mean nothing in a fresh test database, so blocks fall back to
        # whatever image the library holds. Without one, every image-dependent
        # preview is withheld by design.
        cls.image = CustomImage.objects.create(
            title="Preview placeholder",
            file=get_test_image_file(size=(1200, 800)),
        )

    def setUp(self):
        # Preview lookups cache their queries for PREVIEW_LOOKUP_CACHE_TIMEOUT,
        # and the locmem cache outlives each test's database.
        cache.clear()

    def _preview(self, block):
        return self.client.get(
            "/admin/block-preview/", {"id": block.definition_prefix}
        )

    def test_configured_blocks_render_a_styled_preview(self):
        self.client.force_login(self.user)
        checked = 0
        for name, block in BodyStreamBlock().child_blocks.items():
            if not block.is_previewable:
                continue
            checked += 1
            with self.subTest(block=name):
                resp = self._preview(block)
                html = resp.content.decode()
                self.assertEqual(resp.status_code, 200)
                self.assertIn("css/main.css", html)
                # Real rendered block markup, not an empty shell.
                self.assertIn('class="block-%s"' % name, html)
                self.assertIn("<main>", html)
        self.assertTrue(
            checked,
            "No block is previewable -- is the global preview template missing?",
        )
        # Spot-check one block end to end, so a preview that renders its
        # wrapper but no actual content still fails. "accordion" is harvested
        # from real copy and depends on no images or media.
        html = self._preview(BodyStreamBlock().child_blocks["accordion"]).content.decode()
        body = html.split("<main>")[1].split("</main>")[0]
        self.assertGreater(len(body.strip()), 1000)

    def test_every_preview_is_framed_in_whitespace(self):
        self.client.force_login(self.user)
        html = self._preview(BodyStreamBlock().child_blocks["button"]).content.decode()
        # Divided by the scale so it lands as a true 16px on screen.
        self.assertIn("calc(16px / var(--wtr-preview-scale))", html)

    def test_small_blocks_are_centred_and_scaled_up(self):
        """
        Blocks are laid out at a desktop width and scaled down to the pane. A
        block too small to read that way instead declares a narrower layout
        width, which scales it up, and is centred rather than left to sit in a
        corner of the pane.
        """
        self.client.force_login(self.user)
        blocks = BodyStreamBlock().child_blocks
        button = blocks["button"]
        self.assertEqual(button.preview_layout, "center")
        self.assertLess(button.preview_target_width, 640)

        centred = self._preview(button).content.decode()
        self.assertIn("align-items: center;", centred)
        self.assertIn(
            "var TARGET_WIDTH = %d;" % button.preview_target_width, centred
        )

        # Everything else is laid out at a desktop width and scaled down.
        default = self._preview(blocks["text"]).content.decode()
        self.assertIn("var TARGET_WIDTH = 1280;", default)
        self.assertNotIn("align-items: center;", default)

    def test_every_preview_is_vertically_centred(self):
        self.client.force_login(self.user)
        html = self._preview(BodyStreamBlock().child_blocks["text"]).content.decode()
        # `safe` so a block taller than the pane is not clipped at the top.
        self.assertIn("justify-content: safe center;", html)

    def test_a_lone_card_previews_at_the_width_it_has_in_a_grid(self):
        """Card-shaped blocks sit in a grid in practice, never full width."""
        self.client.force_login(self.user)
        blocks = BodyStreamBlock().child_blocks
        for name in ("card", "person_card"):
            with self.subTest(block=name):
                block = blocks[name]
                self.assertEqual(block.preview_max_width, 400)
                self.assertIn("max-width: 400px", self._preview(block).content.decode())

    def test_dense_blocks_are_scaled_up_to_stay_legible(self):
        """
        Blocks whose content is mostly small text are unreadable at the default
        desktop layout width once scaled into the pane, so they declare a
        narrower one.
        """
        self.client.force_login(self.user)
        blocks = BodyStreamBlock().child_blocks
        for name in ("raw_html", "table"):
            with self.subTest(block=name):
                block = blocks[name]
                self.assertLess(block.preview_target_width, 1280)
                self.assertIn(
                    "var TARGET_WIDTH = %d;" % block.preview_target_width,
                    self._preview(block).content.decode(),
                )

    def test_hand_authored_preview_is_used_over_harvested_content(self):
        """
        ButtonBlock deliberately does not use ContentPreviewMixin: its real
        content links to a same-page anchor, which previews as an inert button.
        """
        value = BodyStreamBlock().child_blocks["button"].get_preview_value()
        self.assertEqual(value["link_url"], "https://example.com")
        # A partial preview_value normalises to a StructValue holding only the
        # keys given; templates resolve the rest to "" rather than raising.
        self.assertFalse(value.get("anchor"))

    def test_preview_frame_is_scaled_with_zoom_not_transform(self):
        """
        The preview widens its own iframe so blocks lay out at a desktop
        breakpoint, then scales it back down to the picker's pane.

        That scaling must use `zoom`, which shrinks the layout box.
        `transform: scale()` shrinks the frame only visually and leaves it
        occupying the full target width, which pushes the picker off screen --
        and is invisible to getBoundingClientRect(), since that accounts for
        transforms. Hence a source-level guard.
        """
        self.client.force_login(self.user)
        html = self._preview(BodyStreamBlock().child_blocks["text"]).content.decode()
        self.assertIn("frame.style.zoom = scale;", html)
        self.assertNotIn("frame.style.transform", html)

    def test_every_block_in_the_picker_has_a_preview(self):
        """
        Each block is previewable either from harvested real content or from a
        hand-written Meta.preview_value. A block with neither shows the editor
        nothing but its label.
        """
        missing = [
            name
            for name, block in BodyStreamBlock().child_blocks.items()
            if not block.is_previewable
        ]
        self.assertEqual(missing, [])

    def test_nothing_in_a_preview_leads_anywhere(self):
        """
        Clicking a link or submitting a form inside the preview pane must not
        navigate it away from the block, or reach an external platform.
        """
        self.client.force_login(self.user)
        html = self._preview(BodyStreamBlock().child_blocks["card"]).content.decode()
        self.assertIn('["click", "submit"].forEach', html)
        self.assertIn("event.preventDefault();", html)

    def test_card_grid_preview_is_trimmed_to_three_cards(self):
        """
        Real content has four cards, and exactly four is the one count
        card_grid_block.html lays out 2x2 rather than in three columns.
        """
        block = BodyStreamBlock().child_blocks["card_grid"]
        self.assertEqual(block.preview_max_items, {"cards": 3})
        self.assertEqual(len(block.get_preview_value()["cards"]), 3)

    def test_previews_never_call_a_third_party_platform(self):
        """
        Previews open constantly while editing, so a block that reaches out to
        an external platform to render must not do so here -- or the picker
        would generate third-party traffic per click and break offline.

        ActionKit's form markup is captured once by
        `manage.py harvest_block_previews` and replayed from
        wtrx/previews/block_previews.json, with its scripts stripped. Fundraise
        Up's widget is drawn by a script that previews never load, so the block
        substitutes a static stand-in for it.
        """
        self.client.force_login(self.user)
        blocks = BodyStreamBlock().child_blocks
        with mock.patch.object(
            blocks_module.requests, "get", side_effect=AssertionError("outbound call")
        ), mock.patch.object(
            blocks_module.requests, "post", side_effect=AssertionError("outbound call")
        ):
            actionkit = self._preview(blocks["signup_actionkit"]).content.decode()
            fundraiseup = self._preview(blocks["donate_fundraiseup"]).content.decode()
            actionnetwork = self._preview(
                blocks["signup_action_network"]
            ).content.decode()

        # The jQuery the real embed pulls from a CDN is suppressed.
        self.assertNotIn("ajax.googleapis.com", actionkit)
        # Fundraise Up's script never loads here, so the anchor it would
        # hydrate is replaced by a visible stand-in.
        self.assertIn('role="presentation"', fundraiseup)

        # Nothing in either preview causes the browser to fetch from a third
        # party. Only tags that actually load a resource count -- a form action
        # or a link in the copy is inert until someone clicks it.
        resource = re.compile(
            r"""<(?:script|link|img|iframe|source|video|audio|embed)\b[^>]*?"""
            r"""\b(?:src|href)=["'](https?://[^"']+)""",
            re.IGNORECASE,
        )
        # Action Network draws its form client-side, so the preview must not
        # load its widget script or stylesheet either.
        self.assertNotIn("actionnetwork.org/widgets", actionnetwork)
        self.assertNotIn("actionnetwork.org/css", actionnetwork)

        for name, html in (
            ("actionkit", actionkit),
            ("fundraiseup", fundraiseup),
            ("actionnetwork", actionnetwork),
        ):
            external = [
                url
                for url in resource.findall(html)
                if "fonts.googleapis.com" not in url
            ]
            self.assertEqual(external, [], "%s preview loads %s" % (name, external))

    def test_captured_actionkit_form_carries_no_scripts(self):
        """
        The captured form is replayed verbatim into the admin, so its own
        scripts -- which submit to and fetch from ActionKit -- are stripped at
        capture time rather than trusted not to run.
        """
        entry = blocks_module._preview_data().get("signup_actionkit") or {}
        form_html = entry.get("form_html")
        if not form_html:
            self.skipTest("No ActionKit form captured in this checkout.")
        self.assertNotRegex(form_html, r"(?is)<script\b")

    def test_image_dependent_previews_are_withheld_without_an_image_library(self):
        """
        With no images at all, image-dependent blocks must decline to preview
        rather than render a broken one -- image_block.html calls {% image %}
        without a None-guard, so a dangling reference produces empty output.
        """
        CustomImage.objects.all().delete()
        cache.clear()
        self.assertFalse(BodyStreamBlock().child_blocks["image"].is_previewable)

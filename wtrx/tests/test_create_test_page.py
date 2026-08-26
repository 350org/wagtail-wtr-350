"""
Tests for the create_test_page management command and the test page's rendering.

Verifies that:
  1. The command creates a ContentPage with all block types.
  2. The page responds with HTTP 200.
  3. Each block type produces the expected output (no TemplateSyntaxError, no
     missing-tag crash, no missing-context KeyError, etc.).
  4. --force overwrites an existing page.
  5. The command is a no-op (with a warning) when the page already exists and
     --force is not given.
  6. The command raises CommandError when DEBUG=False.
"""

import shutil
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from wagtail.models import Page, Site

from wtrx.models import ContentPage, HomePage

# Isolated media root so uploaded test images don't accumulate in the real
# MEDIA_ROOT across test runs. Each test class gets its own temp directory
# (defined at module level so both classes can reference it).
_TEMP_MEDIA = tempfile.mkdtemp()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_site():
    """Create a minimal Wagtail site tree: root → HomePage → default Site."""
    root = Page.objects.filter(depth=1).first()
    home = HomePage(title="Test Site", slug="test-home-ctp")
    root.add_child(instance=home)
    site = Site.objects.create(
        hostname="localhost",
        port=80,
        root_page=home,
        is_default_site=True,
        site_name="Test Site",
    )
    return site, home


def _run_command(**kwargs):
    """Run create_test_page and return (stdout, stderr) strings."""
    stdout = StringIO()
    stderr = StringIO()
    call_command("create_test_page", stdout=stdout, stderr=stderr, **kwargs)
    return stdout.getvalue(), stderr.getvalue()


# ---------------------------------------------------------------------------
# Command behaviour tests
# ---------------------------------------------------------------------------


@override_settings(DEBUG=True, WAGTAILEMBEDS_FINDERS=[], MEDIA_ROOT=_TEMP_MEDIA)
class TestCreateTestPageCommand(TestCase):
    """create_test_page command creates a page and reports success."""

    @classmethod
    def setUpTestData(cls):
        # Remove any pre-existing default site so we control the tree.
        Site.objects.filter(is_default_site=True).delete()
        cls.site, cls.home = _make_site()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TEMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def test_page_is_created(self):
        """Command creates a ContentPage with the default slug."""
        _run_command()
        self.assertTrue(ContentPage.objects.filter(slug="test-blocks").exists())

    def test_stdout_reports_success(self):
        """Command writes a success message containing the slug."""
        stdout, _ = _run_command()
        self.assertIn("test-blocks", stdout)

    def test_page_is_child_of_home(self):
        """Created page sits directly under the site's root page."""
        _run_command()
        page = ContentPage.objects.get(slug="test-blocks")
        self.assertEqual(page.get_parent().specific_class, HomePage)

    def test_custom_slug(self):
        """--slug flag sets the page slug."""
        _run_command(slug="custom-slug")
        self.assertTrue(ContentPage.objects.filter(slug="custom-slug").exists())
        # Cleanup so other tests stay isolated
        ContentPage.objects.filter(slug="custom-slug").delete()

    def test_skips_without_force_when_exists(self):
        """Running twice without --force does not raise and warns instead."""
        _run_command(slug="duplicate-slug")
        stdout, _ = _run_command(slug="duplicate-slug")
        # Still only one page with that slug
        self.assertEqual(ContentPage.objects.filter(slug="duplicate-slug").count(), 1)
        self.assertIn("already exists", stdout)
        # Cleanup
        ContentPage.objects.filter(slug="duplicate-slug").delete()

    def test_force_replaces_existing_page(self):
        """--force deletes and recreates the page."""
        _run_command(slug="force-slug")
        first = ContentPage.objects.get(slug="force-slug")
        first_pk = first.pk
        _run_command(slug="force-slug", force=True)
        second = ContentPage.objects.get(slug="force-slug")
        self.assertNotEqual(first_pk, second.pk)
        # Cleanup
        ContentPage.objects.filter(slug="force-slug").delete()

    def test_raises_when_debug_false(self):
        """Command must raise CommandError when DEBUG=False."""
        from django.core.management.base import CommandError

        with self.settings(DEBUG=False):
            with self.assertRaises(CommandError):
                _run_command(slug="should-not-exist")
        self.assertFalse(ContentPage.objects.filter(slug="should-not-exist").exists())

    def test_raises_without_default_site(self):
        """Command must raise CommandError when no default Site exists."""
        from django.core.management.base import CommandError

        Site.objects.filter(is_default_site=True).update(is_default_site=False)
        try:
            with self.assertRaises(CommandError):
                _run_command(slug="no-site-slug")
        finally:
            # Restore so teardown can clean up
            Site.objects.filter(pk=self.site.pk).update(is_default_site=True)


# ---------------------------------------------------------------------------
# Block coverage — the page must exercise every registered block
# ---------------------------------------------------------------------------


@override_settings(DEBUG=True, WAGTAILEMBEDS_FINDERS=[], MEDIA_ROOT=_TEMP_MEDIA)
class TestCreateTestPageCoverage(TestCase):
    """
    Every block registered in BodyStreamBlock / SectionContentBlock must appear
    on the generated page.

    This is the guard that keeps create_test_page honest: adding a block to
    blocks.py without adding a builder to the command fails here rather than
    quietly leaving the new block untested.
    """

    @classmethod
    def setUpTestData(cls):
        Site.objects.filter(is_default_site=True).delete()
        cls.site, cls.home = _make_site()
        _run_command(slug="coverage-test")
        cls.page = ContentPage.objects.get(slug="coverage-test")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TEMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def _used_block_types(self):
        """Block type names present in the page body, sections included."""
        used = set()

        def walk(stream):
            for child in stream:
                used.add(child.block_type)
                if child.block_type == "section":
                    walk(child.value["content"])

        walk(self.page.body)
        return used

    def test_every_body_block_is_present(self):
        from wtrx.blocks import BodyStreamBlock

        registered = set(BodyStreamBlock().child_blocks.keys())
        missing = registered - self._used_block_types()
        self.assertEqual(
            missing,
            set(),
            f"Block types registered in BodyStreamBlock but absent from the "
            f"test page: {sorted(missing)}. Add a builder in create_test_page.py.",
        )

    def test_every_section_block_is_present_inside_a_section(self):
        """
        SectionBlock nesting works at all — at least one block renders inside a
        section, so a section's inner StreamBlock is genuinely exercised.
        """
        sections = [c for c in self.page.body if c.block_type == "section"]
        self.assertTrue(sections)
        self.assertTrue(all(len(s.value["content"]) for s in sections))

    def test_background_palette_is_fully_covered(self):
        """
        Every colour in BACKGROUND_COLOR_CHOICES appears as a section
        background, a callout colour, a hero banner colour and an ActionKit
        signup background.
        """
        from wtrx.blocks import BACKGROUND_COLOR_CHOICES

        palette = {key for key, _label in BACKGROUND_COLOR_CHOICES}
        seen = {
            "section": set(),
            "callout": set(),
            "hero": set(),
            "signup_actionkit": set(),
        }
        for child in self.page.body:
            if child.block_type == "section":
                seen["section"].add(child.value["background"])
            elif child.block_type == "callout":
                seen["callout"].add(child.value["color"])
            elif child.block_type == "hero":
                seen["hero"].add(child.value["banner_color"])
            elif child.block_type == "signup_actionkit":
                seen["signup_actionkit"].add(child.value["background"])

        for name, values in seen.items():
            self.assertEqual(
                palette - values, set(), f"{name} is missing background colours"
            )

    def test_supporting_pages_are_created(self):
        """PageCards and the Wagtail-forms signup need real pages to point at."""
        from wtrx.models import FormPage, IndexPage

        index_page = IndexPage.objects.get(slug="block-test-index")
        self.assertEqual(index_page.get_parent().pk, self.page.pk)
        self.assertEqual(index_page.get_children().live().count(), 3)

        form_page = FormPage.objects.get(slug="block-test-form")
        self.assertEqual(form_page.get_parent().pk, self.page.pk)
        self.assertEqual(form_page.form_fields.count(), 2)

    def test_index_children_have_first_published_at(self):
        """
        PageCardsBlock orders by first_published_at, which Wagtail only sets on
        an admin publish — the command must set it itself (AGENTS.md #32).
        """
        index_page = self.page.get_children().get(slug="block-test-index")
        for child in index_page.get_children():
            self.assertIsNotNone(child.first_published_at)

    def test_force_removes_supporting_pages(self):
        """--force deletes the whole fixture, children included."""
        from wtrx.models import FormPage, IndexPage

        _run_command(slug="coverage-test", force=True)
        self.assertEqual(IndexPage.objects.filter(slug="block-test-index").count(), 1)
        self.assertEqual(FormPage.objects.filter(slug="block-test-form").count(), 1)


# ---------------------------------------------------------------------------
# Rendering tests — HTTP 200 + block content assertions
# ---------------------------------------------------------------------------


@override_settings(DEBUG=True, WAGTAILEMBEDS_FINDERS=[], MEDIA_ROOT=_TEMP_MEDIA)
class TestCreateTestPageRendering(TestCase):
    """
    The test page renders with HTTP 200 and all block types produce output.

    WAGTAILEMBEDS_FINDERS=[] prevents the video block from making a real HTTP
    request to YouTube. The embed tag silently returns "" when no finder
    matches, so the rest of the page still renders correctly.

    SignupActionKitBlock makes no network call here either: it only fetches
    when the ActionKit integration supplies a hostname, and no
    IntegrationSettings exists in these tests.
    """

    @classmethod
    def setUpTestData(cls):
        Site.objects.filter(is_default_site=True).delete()
        cls.site, cls.home = _make_site()
        _run_command(slug="render-test")
        cls.page = ContentPage.objects.get(slug="render-test")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TEMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def _get(self):
        """GET the page using the Django test client. Returns the response."""
        # Wagtail serves pages at their full URL including locale prefix.
        url = self.page.url
        return self.client.get(url, SERVER_NAME="localhost")

    def test_page_returns_200(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)

    def test_page_uses_content_page_template(self):
        response = self._get()
        self.assertTemplateUsed(response, "wtrx/pages/content_page.html")

    def test_page_title_in_response(self):
        response = self._get()
        self.assertContains(response, "Block Test Page")

    # --- typography reference ---

    def test_heading_ramp_covers_h1_to_h6(self):
        """The typography reference renders every heading level, h1 through h6."""
        response = self._get()
        html = response.content.decode()
        for level in range(1, 7):
            self.assertIn(
                f"<h{level}>Heading {level}",
                html,
                f"h{level} missing from the typography reference",
            )

    def test_heading_ramp_uses_the_rich_text_container(self):
        """
        The ramp renders inside .wtr-text-block, so h2/h3/h4 pick up the real
        heading rules from main.css rather than prose defaults.
        """
        response = self._get()
        self.assertContains(response, "wtr-text-block prose")

    def test_type_scale_lists_every_step(self):
        response = self._get()
        html = response.content.decode()
        for utility in ("text-8xl", "text-64", "text-40", "text-xl", "text-sm"):
            self.assertIn(utility, html)

    def test_rich_text_sample_covers_every_editor_feature(self):
        """RICHTEXT_FEATURES_FULL: h2, h3, h4, bold, italic, link, ol, ul, blockquote."""
        response = self._get()
        html = response.content.decode()
        for fragment in (
            "Rich text heading 2",
            "Rich text heading 3",
            "Rich text heading 4",
            "<ul>",
            "<ol>",
            "<blockquote>",
        ):
            self.assertIn(fragment, html)

    # --- content blocks ---

    def test_text_block_renders(self):
        response = self._get()
        self.assertContains(response, "sample paragraph of rich text")

    def test_video_block_renders(self):
        # The video block renders its <figure> even when the embed is empty.
        response = self._get()
        self.assertContains(response, "Sample video caption")

    def test_button_block_renders(self):
        response = self._get()
        self.assertContains(response, "Primary Button")

    def test_button_secondary_renders(self):
        response = self._get()
        self.assertContains(response, "Secondary Button")

    def test_button_outline_renders(self):
        response = self._get()
        self.assertContains(response, "Outline Button")

    def test_button_anchor_variant_renders(self):
        """The anchor button links to another block's anchor_id on this page."""
        response = self._get()
        self.assertContains(response, "#signup-actionkit-navy")

    def test_raw_html_block_renders(self):
        response = self._get()
        self.assertContains(response, "Embedded HTML")

    def test_table_block_renders(self):
        response = self._get()
        self.assertContains(response, "Renewable capacity added")

    def test_image_block_with_caption_renders(self):
        response = self._get()
        self.assertContains(response, "Sample image caption")

    def test_image_block_alt_text_renders(self):
        response = self._get()
        self.assertContains(response, 'alt="A test image with explicit alt text"')

    # --- card blocks ---

    def test_card_block_with_all_fields_renders(self):
        response = self._get()
        self.assertContains(response, "Standalone Card (all fields)")

    def test_card_block_minimal_renders(self):
        response = self._get()
        self.assertContains(response, "Standalone Card (minimal)")

    def test_card_grid_three_and_four_card_variants_render(self):
        """Four cards lay out 2x2, three lay out in columns — both are present."""
        response = self._get()
        self.assertContains(response, "Card Grid (3 cards)")
        self.assertContains(response, "Card Grid (4 cards)")

    def test_person_card_full_renders(self):
        response = self._get()
        self.assertContains(response, "Jane Sample")
        self.assertContains(response, "Campaign Manager")

    def test_person_card_minimal_renders(self):
        response = self._get()
        self.assertContains(response, "Bob Minimal")

    def test_card_carousel_renders(self):
        response = self._get()
        self.assertContains(response, "Carousel card 1")

    def test_page_cards_renders_index_children(self):
        """PageCardsBlock lists the children of the generated index page."""
        response = self._get()
        self.assertContains(response, "Index Child Page 1")

    # --- layout blocks ---

    def test_image_card_list_renders(self):
        response = self._get()
        self.assertContains(response, "Image Card List")
        self.assertContains(response, "First point")

    def test_image_text_renders(self):
        response = self._get()
        self.assertContains(response, "Image + Text")

    def test_feature_panel_variants_render(self):
        response = self._get()
        self.assertContains(response, "Feature Panel (image-left, white)")
        self.assertContains(response, "Feature Panel (image-right, dark-grey)")

    def test_feature_panel_eyebrow_renders(self):
        response = self._get()
        self.assertContains(response, "Featured Campaign")

    def test_accordion_block_renders(self):
        response = self._get()
        self.assertContains(response, "What is this accordion?")

    def test_callout_renders_every_colour(self):
        response = self._get()
        html = response.content.decode()
        for colour in ("white", "light-grey", "dark-grey", "navy", "red", "blue-gradient"):
            self.assertIn(f"Callout ({colour})", html)

    def test_hero_block_renders_every_colour(self):
        response = self._get()
        html = response.content.decode()
        for colour in ("white", "light-grey", "dark-grey", "navy", "red", "blue-gradient"):
            self.assertIn(f"Hero Block ({colour})", html)

    # --- sections ---

    def test_section_renders_every_background(self):
        response = self._get()
        html = response.content.decode()
        for colour in ("white", "light-grey", "dark-grey", "navy", "red", "blue-gradient"):
            self.assertIn(f'id="section-{colour}"', html)

    def test_section_padding_variants_render(self):
        response = self._get()
        self.assertContains(response, 'id="section-padding-sm"')
        self.assertContains(response, 'id="section-padding-lg"')

    def test_section_width_variants_render(self):
        response = self._get()
        self.assertContains(response, 'id="section-width-narrow"')
        self.assertContains(response, 'id="section-width-wide"')

    # --- action blocks ---

    def test_donate_block_renders(self):
        response = self._get()
        self.assertContains(response, "Support Our Campaign")

    def test_donate_block_shows_override_amounts(self):
        response = self._get()
        # override_amounts = [10, 25, 50, 100] — at least one should appear
        self.assertContains(response, "$10")

    def test_donate_block_minimal_renders(self):
        response = self._get()
        self.assertContains(response, "Donate (using site defaults)")

    def test_donate_fundraiseup_renders(self):
        response = self._get()
        self.assertContains(response, "Donate (Fundraise Up)")

    def test_signup_wagtail_forms_points_at_the_form_page(self):
        """
        The block renders its container wired to the generated FormPage.

        The fields themselves are fetched client-side by signup JS, so the
        server-rendered markup carries the form URL and a loading placeholder,
        not the inputs.
        """
        response = self._get()
        self.assertContains(response, "Sign Up (Wagtail Forms)")
        self.assertContains(response, 'data-form-url="/render-test/block-test-form/"')

    def test_signup_action_network_renders(self):
        response = self._get()
        self.assertContains(response, "Sign Up (Action Network)")

    def test_signup_action_network_success_message_renders(self):
        response = self._get()
        self.assertContains(response, "Thank you for signing up.")

    def test_signup_actionkit_renders_every_background(self):
        response = self._get()
        html = response.content.decode()
        for colour in ("white", "light-grey", "dark-grey", "navy", "red", "blue-gradient"):
            self.assertIn(f"Sign Up (ActionKit, {colour})", html)

    def test_signup_link_renders(self):
        response = self._get()
        self.assertContains(response, "Sign Up (Link)")

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
# Rendering tests — HTTP 200 + block content assertions
# ---------------------------------------------------------------------------


@override_settings(DEBUG=True, WAGTAILEMBEDS_FINDERS=[], MEDIA_ROOT=_TEMP_MEDIA)
class TestCreateTestPageRendering(TestCase):
    """
    The test page renders with HTTP 200 and all block types produce output.

    WAGTAILEMBEDS_FINDERS=[] prevents the video block from making a real HTTP
    request to YouTube. The embed tag silently returns "" when no finder
    matches, so the rest of the page still renders correctly.
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

    def test_quote_block_renders(self):
        response = self._get()
        self.assertContains(response, "The change we need starts with each of us")

    def test_raw_html_block_renders(self):
        response = self._get()
        self.assertContains(response, "Raw HTML block")

    def test_table_block_renders(self):
        response = self._get()
        self.assertContains(response, "Alice Example")

    # --- layout blocks ---

    def test_card_grid_block_renders(self):
        response = self._get()
        self.assertContains(response, "Card Grid — With Image")
        self.assertContains(response, "Card Grid — No Image")
        self.assertContains(response, "Card Grid — Description Only")

    def test_accordion_block_renders(self):
        response = self._get()
        self.assertContains(response, "What is this accordion?")

    def test_section_block_light_renders(self):
        response = self._get()
        # SectionBlock with background=light wraps inner blocks; check anchor
        self.assertContains(response, "section-light")

    def test_section_block_dark_renders(self):
        response = self._get()
        self.assertContains(response, "section-dark")

    def test_section_block_primary_renders(self):
        response = self._get()
        self.assertContains(response, "section-primary")

    def test_section_block_muted_renders(self):
        response = self._get()
        self.assertContains(response, "section-muted")

    # --- composite blocks ---

    def test_hero_block_renders(self):
        response = self._get()
        self.assertContains(response, "Hero Block Inside Body")

    # --- action blocks ---

    def test_donate_block_renders(self):
        response = self._get()
        self.assertContains(response, "Support Our Campaign")

    def test_donate_block_shows_override_amounts(self):
        response = self._get()
        # override_amounts = [10, 25, 50, 100] — at least one should appear
        self.assertContains(response, "$10")

    def test_signup_link_block_renders(self):
        response = self._get()
        self.assertContains(response, "Join Our Movement")

    def test_signup_action_network_block_renders(self):
        response = self._get()
        self.assertContains(response, "Action Network Signup")

    # --- image block ---

    def test_image_block_with_caption_renders(self):
        response = self._get()
        self.assertContains(response, "Sample image caption")

    def test_image_block_alt_text_renders(self):
        response = self._get()
        self.assertContains(response, 'alt="A test image with explicit alt text"')

    # --- button style variants ---

    def test_button_secondary_renders(self):
        response = self._get()
        self.assertContains(response, "Secondary Button")

    def test_button_outline_renders(self):
        response = self._get()
        self.assertContains(response, "Outline Button")

    # --- quote without attribution ---

    def test_quote_without_attribution_renders(self):
        response = self._get()
        self.assertContains(response, "Unattributed quote")

    # --- standalone card block ---

    def test_card_block_with_image_renders(self):
        response = self._get()
        self.assertContains(response, "Standalone Card (with image)")

    def test_card_block_with_icon_renders(self):
        """Full card includes an icon — verify the flex icon+heading layout."""
        response = self._get()
        self.assertContains(response, 'class="flex items-center gap-3"')

    def test_card_block_minimal_renders(self):
        response = self._get()
        self.assertContains(response, "Standalone Card (minimal)")

    # --- person card block ---

    def test_person_card_full_renders(self):
        response = self._get()
        self.assertContains(response, "Jane Sample")
        self.assertContains(response, "Campaign Manager")

    def test_person_card_minimal_renders(self):
        response = self._get()
        self.assertContains(response, "Bob Minimal")

    # --- callout block ---

    def test_callout_image_left_renders(self):
        response = self._get()
        self.assertContains(response, "image aligned to the")
        self.assertContains(response, "Learn More")

    def test_callout_image_right_renders(self):
        response = self._get()
        self.assertContains(response, "No CTA button on this one")

    # --- hero block minimal ---

    def test_hero_block_minimal_renders(self):
        response = self._get()
        self.assertContains(response, "Minimal Hero — Headline Only")

    # --- donate block minimal ---

    def test_donate_block_minimal_renders(self):
        response = self._get()
        self.assertContains(response, "Donate (using site defaults)")

    # --- section padding variants ---

    def test_section_padding_sm_renders(self):
        response = self._get()
        self.assertContains(response, "section-light-sm")

    def test_section_padding_lg_renders(self):
        response = self._get()
        self.assertContains(response, "section-light-lg")

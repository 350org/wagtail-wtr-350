"""
Tests for the per-site integration config StructBlocks
(wtrx/integrations/*.py) — specifically the required-field audit: a config
field an integration cannot function without (a URL, hostname, or
credential) must be `required=True` at the block level, not just
documented as needed. ActBlueConfigBlock.base_url was the confirmed gap —
`required=False` let an editor enable ActBlue with no destination URL,
producing a DonateBlock that rendered a broken/empty link. See AGENTS.md
rule #10's DonateBlock note and pitfall history for the original bug.
"""

from django.test import SimpleTestCase

from wtrx.integrations.action_network import ActionNetworkConfigBlock
from wtrx.integrations.actblue import ActBlueConfigBlock
from wtrx.integrations.actionkit import ActionKitConfigBlock
from wtrx.integrations.fundraiseup import FundraiseUpConfigBlock
from wtrx.integrations.gtm import GoogleTagManagerConfigBlock
from wtrx.integrations.registry import get_integration
from wtrx.integrations.wagtail_forms import WagtailFormsConfigBlock


class TestActBlueConfigBlockRequiredFields(SimpleTestCase):
    def test_base_url_is_required(self):
        """
        The confirmed gap: base_url used to be required=False even though
        DonateBlock is non-functional without it (no override URL set on
        the block itself falls straight through to this).
        """
        block = ActBlueConfigBlock()
        self.assertTrue(block.declared_blocks["base_url"].required)

    def test_enabled_is_not_required(self):
        # BooleanBlock's own required=False, deliberately -- a checkbox
        # that can't be left unchecked would be a contradiction.
        block = ActBlueConfigBlock()
        self.assertFalse(block.declared_blocks["enabled"].required)

    def test_suggested_amounts_stays_optional(self):
        # DonateBlock has its own per-instance suggested_amounts override
        # and falls back to nothing shown rather than breaking when blank.
        block = ActBlueConfigBlock()
        self.assertFalse(block.declared_blocks["suggested_amounts"].required)


class TestActionKitConfigBlockRequiredFields(SimpleTestCase):
    """hostname/api_username were already correctly required; pinned here
    so a future edit can't silently loosen them."""

    def test_hostname_is_required(self):
        block = ActionKitConfigBlock()
        self.assertTrue(block.declared_blocks["hostname"].required)

    def test_api_username_is_required(self):
        block = ActionKitConfigBlock()
        self.assertTrue(block.declared_blocks["api_username"].required)

    def test_api_password_stays_optional(self):
        # Deliberately optional: WTRX_ACTIONKIT_API_PASSWORD (an env var)
        # is the preferred way to set this in production.
        block = ActionKitConfigBlock()
        self.assertFalse(block.declared_blocks["api_password"].required)


class TestFundraiseUpConfigBlockRequiredFields(SimpleTestCase):
    def test_installation_code_is_required(self):
        block = FundraiseUpConfigBlock()
        self.assertTrue(block.declared_blocks["installation_code"].required)

    def test_element_id_fields_stay_optional(self):
        # A site can configure just element_id_default and none of the
        # region-specific ones.
        block = FundraiseUpConfigBlock()
        for field_name in (
            "element_id_us",
            "element_id_nl",
            "element_id_ca",
            "element_id_gb",
            "element_id_eu",
            "element_id_default",
        ):
            with self.subTest(field=field_name):
                self.assertFalse(block.declared_blocks[field_name].required)


class TestActionNetworkConfigBlockRequiredFields(SimpleTestCase):
    def test_api_key_stays_optional(self):
        # Only needed for a not-yet-built server-side path; the embed
        # widget approach (what's actually used today) needs no API key.
        block = ActionNetworkConfigBlock()
        self.assertFalse(block.declared_blocks["api_key"].required)


class TestWagtailFormsConfigBlockRequiredFields(SimpleTestCase):
    def test_has_no_config_fields_beyond_enabled(self):
        block = WagtailFormsConfigBlock()
        self.assertEqual(set(block.declared_blocks.keys()), {"enabled"})


class TestGoogleTagManagerConfigBlock(SimpleTestCase):
    """
    GoogleTagManagerConfigBlock (wtrx/integrations/gtm.py) -- the editor
    pastes Google's own setup snippet(s) verbatim (same pattern as
    FundraiseUpConfigBlock.installation_code), so head_snippet is the one
    required config field; body_snippet (Tag Manager's <noscript>
    fallback) is optional since a standalone Analytics-only setup has no
    equivalent to paste.
    """

    def test_has_expected_fields(self):
        block = GoogleTagManagerConfigBlock()
        self.assertEqual(
            set(block.declared_blocks.keys()), {"enabled", "head_snippet", "body_snippet"}
        )

    def test_head_snippet_is_required(self):
        block = GoogleTagManagerConfigBlock()
        self.assertTrue(block.declared_blocks["head_snippet"].required)

    def test_body_snippet_stays_optional(self):
        block = GoogleTagManagerConfigBlock()
        self.assertFalse(block.declared_blocks["body_snippet"].required)

    def test_enabled_is_not_required(self):
        block = GoogleTagManagerConfigBlock()
        self.assertFalse(block.declared_blocks["enabled"].required)

    def test_registered_with_head_and_body_html_fields(self):
        """
        Confirms this is wired into IntegrationType.head_html_field/
        body_html_field (registry.py) with the right field names -- what
        actually makes IntegrationSettings.head_html()/body_html()
        (site_settings.py) pick this integration's snippets up.
        """
        integration_type = get_integration("google_tag_manager")
        self.assertIsNotNone(integration_type)
        self.assertEqual(integration_type.head_html_field, "head_snippet")
        self.assertEqual(integration_type.body_html_field, "body_snippet")
        self.assertEqual(integration_type.content_block_names, ())

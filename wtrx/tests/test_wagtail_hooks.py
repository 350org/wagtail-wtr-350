"""
Tests for wagtail_hooks.py.

Block-type visibility is no longer a hook in this file — see
wtrx/tests/test_blocks.py's TestIntegrationGatedStreamBlockVisibility for
that behavior, which now lives in IntegrationGatedStreamBlockMixin
(wtrx/blocks/__init__.py). The registry-metadata tests below still belong
here since they're about the IntegrationType contract, not the hook file.
"""

from django.test import TestCase

from wtrx.integrations.registry import get_integration


class TestIntegrationRegistryMetadata(TestCase):
    """
    Verify the block-visibility metadata each integration declares.

    wagtail_hooks.py has no hardcoded per-integration mapping anymore — it
    reads this metadata straight off the registry, so these tests guard the
    contract each integration module must uphold.
    """

    def test_actionkit_gates_signup_actionkit_block(self):
        integration_type = get_integration("actionkit")
        self.assertEqual(integration_type.category, "signup")
        self.assertEqual(integration_type.content_block_names, ("signup_actionkit",))

    def test_fundraiseup_gates_donate_fundraiseup_block(self):
        integration_type = get_integration("fundraiseup")
        self.assertEqual(integration_type.category, "donation")
        self.assertEqual(integration_type.content_block_names, ("donate_fundraiseup",))

    def test_actblue_gates_donate_block(self):
        integration_type = get_integration("actblue")
        self.assertEqual(integration_type.category, "donation")
        self.assertEqual(integration_type.content_block_names, ("donate",))

    def test_action_network_gates_signup_action_network_block(self):
        integration_type = get_integration("action_network")
        self.assertEqual(integration_type.category, "signup")
        self.assertEqual(
            integration_type.content_block_names, ("signup_action_network",)
        )

    def test_wagtail_forms_gates_signup_wagtail_forms_block(self):
        """
        Wagtail Forms is a built-in feature, not a third-party integration —
        it's registered with default_enabled=True so its block stays visible
        out of the box, hideable only by an explicit disabled entry (or by
        enabling a real signup integration — see
        IntegrationSettings.is_integration_enabled()'s category-yielding
        rule).
        """
        integration_type = get_integration("wagtail_forms")
        self.assertEqual(integration_type.category, "signup")
        self.assertEqual(
            integration_type.content_block_names, ("signup_wagtail_forms",)
        )
        self.assertTrue(integration_type.default_enabled)

    def test_only_built_in_pseudo_integrations_default_to_enabled(self):
        """
        Every genuine third-party integration must stay hidden until a site
        explicitly configures and enables it — default_enabled=True should
        never spread to one of them by accident. Only a built-in,
        zero-configuration option (currently just Wagtail Forms) may set it.
        """
        for slug in ("actionkit", "fundraiseup", "actblue", "action_network"):
            integration_type = get_integration(slug)
            self.assertFalse(
                integration_type.default_enabled,
                f"{slug} should not default to enabled",
            )

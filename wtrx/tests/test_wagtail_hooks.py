"""
Tests for wagtail_hooks.py — block visibility hooks.
"""

from django.test import RequestFactory, TestCase
from wagtail.models import Site

from wtrx.integrations.registry import get_integration
from wtrx.site_settings import IntegrationSettings
from wtrx.wagtail_hooks import _block_visibility_js


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


class TestBlockVisibilityJS(TestCase):
    """Test the _block_visibility_js view function."""

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.get(is_default_site=True)
        cls.integration, _ = IntegrationSettings.objects.get_or_create(
            site=cls.site,
        )

    def _make_request(self):
        request = RequestFactory().get("/admin/wtrx/block-visibility.js")
        request.META["HTTP_HOST"] = self.site.hostname
        request.META["SERVER_PORT"] = str(self.site.port)
        return request

    def _set_integrations(self, data):
        self.integration.integrations = data
        self.integration.save()

    def test_returns_javascript_content_type(self):
        response = _block_visibility_js(self._make_request())
        self.assertEqual(response["Content-Type"], "application/javascript")

    def test_no_integrations_hides_all_gated_blocks(self):
        """With nothing configured, every integration-gated block is hidden."""
        self._set_integrations([])
        response = _block_visibility_js(self._make_request())
        content = response.content.decode()
        for name in (
            "donate",
            "donate_fundraiseup",
            "signup_actionkit",
            "signup_action_network",
        ):
            self.assertIn(f'data-contentpath=\\"{name}\\"', content)

    def test_enabled_actblue_shows_donate_hides_fundraiseup(self):
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
        response = _block_visibility_js(self._make_request())
        content = response.content.decode()
        self.assertNotIn('data-contentpath=\\"donate\\"', content)
        self.assertIn('data-contentpath=\\"donate_fundraiseup\\"', content)

    def test_disabled_entry_is_treated_as_not_enabled(self):
        """An entry present but with enabled=False still hides its block."""
        self._set_integrations(
            [
                (
                    "actionkit",
                    {
                        "enabled": False,
                        "hostname": "x.actionkit.com",
                        "api_username": "u",
                        "api_password": "",
                    },
                )
            ]
        )
        response = _block_visibility_js(self._make_request())
        content = response.content.decode()
        self.assertIn('data-contentpath=\\"signup_actionkit\\"', content)

    def test_multiple_signup_integrations_can_be_enabled_simultaneously(self):
        """Independent toggles: ActionKit and Action Network can both be enabled at once."""
        self._set_integrations(
            [
                (
                    "actionkit",
                    {
                        "enabled": True,
                        "hostname": "x.actionkit.com",
                        "api_username": "u",
                        "api_password": "",
                    },
                ),
                ("action_network", {"enabled": True, "api_key": ""}),
            ]
        )
        response = _block_visibility_js(self._make_request())
        content = response.content.decode()
        self.assertNotIn('data-contentpath=\\"signup_actionkit\\"', content)
        self.assertNotIn('data-contentpath=\\"signup_action_network\\"', content)

    def test_signup_wagtail_forms_and_signup_link_never_hidden(self):
        """These two blocks aren't gated by any integration."""
        self._set_integrations([])
        response = _block_visibility_js(self._make_request())
        content = response.content.decode()
        self.assertNotIn('data-contentpath=\\"signup_wagtail_forms\\"', content)
        self.assertNotIn('data-contentpath=\\"signup_link\\"', content)

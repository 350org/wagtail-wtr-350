"""
Tests for wagtail_hooks.py — block visibility hooks.
"""

from django.test import RequestFactory, TestCase
from wagtail.models import Site

from wtrx.site_settings import IntegrationSettings
from wtrx.wagtail_hooks import (
    BLOCK_PLATFORM_REQUIREMENTS,
    _block_visibility_js,
)


class TestBlockPlatformRequirements(TestCase):
    """Verify the BLOCK_PLATFORM_REQUIREMENTS mapping."""

    def test_donate_requires_donation_platform(self):
        self.assertIn("donate", BLOCK_PLATFORM_REQUIREMENTS)
        category, value = BLOCK_PLATFORM_REQUIREMENTS["donate"]
        self.assertEqual(category, "donation")
        self.assertIsNone(value)

    def test_signup_wagtail_forms_requires_matching_platform(self):
        self.assertIn("signup_wagtail_forms", BLOCK_PLATFORM_REQUIREMENTS)
        category, value = BLOCK_PLATFORM_REQUIREMENTS["signup_wagtail_forms"]
        self.assertEqual(category, "signup")
        self.assertEqual(value, "wagtail_forms")

    def test_signup_action_network_requires_matching_platform(self):
        self.assertIn("signup_action_network", BLOCK_PLATFORM_REQUIREMENTS)
        category, value = BLOCK_PLATFORM_REQUIREMENTS["signup_action_network"]
        self.assertEqual(category, "signup")
        self.assertEqual(value, "action_network")

    def test_signup_link_not_in_requirements(self):
        """signup_link is platform-agnostic and should not be in the mapping."""
        self.assertNotIn("signup_link", BLOCK_PLATFORM_REQUIREMENTS)


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

    def test_returns_javascript_content_type(self):
        response = _block_visibility_js(self._make_request())
        self.assertEqual(response["Content-Type"], "application/javascript")

    def test_no_donation_hides_donate_block(self):
        """When donation_platform is 'none', the donate block should be hidden."""
        self.integration.donation_platform = "none"
        self.integration.signup_platform = "wagtail_forms"
        self.integration.save()
        response = _block_visibility_js(self._make_request())
        content = response.content.decode()
        self.assertIn("donate", content)
        self.assertIn("display: none", content)

    def test_actblue_does_not_hide_donate_block(self):
        """When donation_platform is 'actblue', the donate block should NOT be hidden."""
        self.integration.donation_platform = "actblue"
        self.integration.signup_platform = "wagtail_forms"
        self.integration.save()
        response = _block_visibility_js(self._make_request())
        content = response.content.decode()
        # donate should not appear in CSS selectors
        self.assertNotIn('[data-contentpath="donate"]', content)

    def test_wagtail_forms_hides_action_network(self):
        """When signup_platform is 'wagtail_forms', action_network block should be hidden."""
        self.integration.donation_platform = "actblue"
        self.integration.signup_platform = "wagtail_forms"
        self.integration.save()
        response = _block_visibility_js(self._make_request())
        content = response.content.decode()
        self.assertIn("signup_action_network", content)
        self.assertNotIn("signup_wagtail_forms", content)

    def test_action_network_hides_wagtail_forms(self):
        """When signup_platform is 'action_network', wagtail_forms block should be hidden."""
        self.integration.donation_platform = "actblue"
        self.integration.signup_platform = "action_network"
        self.integration.save()
        response = _block_visibility_js(self._make_request())
        content = response.content.decode()
        self.assertIn("signup_wagtail_forms", content)
        self.assertNotIn("signup_action_network", content)

    def test_active_platforms_not_hidden(self):
        """Active platform blocks should not be hidden in the CSS."""
        self.integration.donation_platform = "actblue"
        self.integration.signup_platform = "wagtail_forms"
        self.integration.save()
        response = _block_visibility_js(self._make_request())
        content = response.content.decode()
        # donate and wagtail_forms are active — should not be hidden
        self.assertNotIn('[data-contentpath="donate"]', content)
        self.assertNotIn('[data-contentpath="signup_wagtail_forms"]', content)

"""
Tests for the setup_site management command.
"""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from wagtail.models import Page, Site

from wtrx.models import HomePage
from wtrx.site_settings import IntegrationSettings


class TestSetupSiteCommand(TestCase):
    """Test the setup_site management command with mocked input."""

    # Numbered menu positions (1-indexed):
    #   Language:  1=en (only configured language in test settings)
    #   Donation:  1=none, 2=actblue
    #   Signup:    1=wagtail_forms, 2=action_network, 3=none

    def _call_setup(self, inputs):
        """
        Call the setup_site command with a sequence of mocked input() responses.

        Returns (stdout, stderr) as strings.
        """
        stdout = StringIO()
        stderr = StringIO()
        with patch("builtins.input", side_effect=inputs):
            call_command("setup_site", stdout=stdout, stderr=stderr)
        return stdout.getvalue(), stderr.getvalue()

    def test_creates_homepage_and_site(self):
        """Command creates a HomePage and default Site with the given name."""
        Site.objects.filter(is_default_site=True).delete()

        inputs = [
            "Test Campaign",  # site name (free text)
            "1",  # language: 1=en
            "1",  # donation platform: 1=none
            "1",  # signup platform: 1=wagtail_forms
        ]
        stdout, _stderr = self._call_setup(inputs)

        self.assertIn("Setup complete", stdout)

        home = HomePage.objects.first()
        self.assertIsNotNone(home)
        self.assertEqual(home.title, "Test Campaign")

        site = Site.objects.get(is_default_site=True)
        self.assertEqual(site.site_name, "Test Campaign")
        self.assertEqual(site.root_page_id, home.pk)

    def test_creates_integration_settings(self):
        """Command creates IntegrationSettings with the chosen platforms."""
        Site.objects.filter(is_default_site=True).delete()

        inputs = [
            "My Org",  # site name
            "1",  # language: 1=en
            "2",  # donation platform: 2=actblue
            "https://secure.actblue.com/donate/myorg",  # donation URL
            "10,25,50,100",  # suggested amounts
            "2",  # signup platform: 2=action_network
        ]
        stdout, _stderr = self._call_setup(inputs)

        site = Site.objects.get(is_default_site=True)
        integration = IntegrationSettings.objects.get(site=site)
        self.assertEqual(integration.donation_platform, "actblue")
        self.assertEqual(
            integration.donation_base_url,
            "https://secure.actblue.com/donate/myorg",
        )
        self.assertEqual(integration.donation_suggested_amounts, "10,25,50,100")
        self.assertEqual(integration.signup_platform, "action_network")

    def test_reuses_existing_homepage(self):
        """If a HomePage already exists, the command reuses it."""
        root = Page.objects.filter(depth=1).first()
        existing = HomePage(title="Existing Home", slug="existing-home")
        root.add_child(instance=existing)

        Site.objects.filter(is_default_site=True).delete()

        inputs = [
            "New Name",  # site name
            "1",  # language: 1=en
            "1",  # donation platform: 1=none
            "1",  # signup platform: 1=wagtail_forms
        ]
        stdout, _stderr = self._call_setup(inputs)

        self.assertEqual(HomePage.objects.count(), 1)
        self.assertIn("already exists", stdout)

    def test_updates_existing_default_site(self):
        """If a default Site already exists, the command updates it."""
        inputs = [
            "Updated Name",  # site name
            "1",  # language: 1=en
            "1",  # donation platform: 1=none
            "3",  # signup platform: 3=none
        ]
        stdout, _stderr = self._call_setup(inputs)

        site = Site.objects.get(is_default_site=True)
        self.assertEqual(site.site_name, "Updated Name")

    def test_defaults_accepted(self):
        """Pressing Enter on all prompts uses defaults and completes successfully."""
        Site.objects.filter(is_default_site=True).delete()

        # Empty strings -> all defaults: "My Site", en, none, wagtail_forms
        inputs = ["", "", "", ""]
        stdout, _stderr = self._call_setup(inputs)

        self.assertIn("Setup complete", stdout)
        site = Site.objects.get(is_default_site=True)
        self.assertEqual(site.site_name, "My Site")

        integration = IntegrationSettings.objects.get(site=site)
        self.assertEqual(integration.donation_platform, "none")
        self.assertEqual(integration.signup_platform, "wagtail_forms")

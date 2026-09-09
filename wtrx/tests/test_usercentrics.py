"""
Tests for the Usercentrics consent snippet (wtrx/templates/wtrx/includes/
usercentrics_head.html), configured via Settings > Integrations (see
wtrx.integrations.usercentrics and
IntegrationSettings.get_usercentrics_config()).

dev.py sets WTRX_USERCENTRICS_DISABLED=True (the local-dev kill switch, see
that setting's own docstring), so every test that expects the banner to
actually render overrides it back to False -- same reason the pre-migration
version of this file always overrode WTRX_USERCENTRICS_SETTINGS_ID.

Only the template's conditional structure is testable server-side here — the
runtime /cdn-cgi/trace fetch, its "loc=" parsing, the timeout race, and real
banner show/hide behavior all require a real Cloudflare-proxied environment
and are covered by manual QA instead (see AGENTS.md).
"""

from django.test import TestCase, override_settings
from wagtail.models import Page, Site

from wtrx.models import HomePage
from wtrx.site_settings import IntegrationSettings


@override_settings(WTRX_USERCENTRICS_DISABLED=False)
class TestUsercentricsHeadRendering(TestCase):
    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        home = HomePage(title="Test Site", slug="test-home-uc")
        root.add_child(instance=home)
        cls.site = Site.objects.create(
            hostname="uc-test.localhost",
            port=80,
            root_page=home,
            is_default_site=False,
            site_name="Test Site",
        )
        cls.integration, _ = IntegrationSettings.objects.get_or_create(site=cls.site)

    def _get(self):
        return self.client.get("/", HTTP_HOST=self.site.hostname)

    def _set_usercentrics(self, **overrides):
        value = {
            "enabled": True,
            "settings_id": "test-id",
            "script_version": "1.1.4",
            "reload_on_opt_in_service_ids": "",
            "deactivate_blocking_service_ids": "",
            "fallback_country": "DE",
            "manual_country_override": "",
        }
        value.update(overrides)
        self.integration.integrations = [("usercentrics", value)]
        self.integration.save()

    def test_disabled_when_no_integration_entry(self):
        self.integration.integrations = []
        self.integration.save()
        response = self._get()
        self.assertNotContains(response, "gtag(")
        self.assertNotContains(response, "UsercentricsConsent")

    def test_disabled_when_entry_not_enabled(self):
        self._set_usercentrics(enabled=False)
        response = self._get()
        self.assertNotContains(response, "gtag(")
        self.assertNotContains(response, "UsercentricsConsent")

    @override_settings(WTRX_USERCENTRICS_DISABLED=True)
    def test_disabled_by_kill_switch_even_when_configured(self):
        self._set_usercentrics()
        response = self._get()
        self.assertNotContains(response, "gtag(")
        self.assertNotContains(response, "UsercentricsConsent")

    def test_fetches_trace_when_no_country_override(self):
        self._set_usercentrics(manual_country_override="")
        response = self._get()
        content = response.content.decode()
        self.assertIn("fetch('/cdn-cgi/trace')", content)
        # The override branch calls loadUsercentrics with a literal quoted
        # country code; the fetch/timeout paths only ever pass a variable
        # (FALLBACK_COUNTRY or the parsed match), so this pattern's absence
        # confirms the override branch was skipped.
        self.assertNotRegex(content, r"loadUsercentrics\('[A-Z]{2}'\)")
        # Consent Mode default must appear before the country/init block.
        self.assertLess(
            content.index("gtag('consent', 'default'"),
            content.index("fetch('/cdn-cgi/trace')"),
        )

    def test_country_override_skips_trace_fetch(self):
        self._set_usercentrics(manual_country_override="FR")
        response = self._get()
        content = response.content.decode()
        self.assertIn("loadUsercentrics('FR')", content)
        self.assertNotIn("cdn-cgi/trace", content)

    def test_settings_id_and_version_interpolated(self):
        self._set_usercentrics(settings_id="test123id", script_version="9.9.9")
        response = self._get()
        content = response.content.decode()
        self.assertIn("usercentrics-consent/9.9.9/usercentrics-consent.js", content)
        self.assertIn("settingsId: 'test123id'", content)

    def test_service_ids_split_from_comma_separated_config(self):
        # |escapejs renders a hyphen as -, so use ids without one to
        # keep this assertion about the split(',') wiring, not escaping.
        self._set_usercentrics(
            reload_on_opt_in_service_ids="ServiceOne",
            deactivate_blocking_service_ids="ServiceTwo, ServiceThree",
        )
        response = self._get()
        content = response.content.decode()
        self.assertIn("'ServiceOne'.split(','", content)
        self.assertIn("'ServiceTwo, ServiceThree'.split(','", content)

    def test_fallback_country_interpolated(self):
        self._set_usercentrics(fallback_country="FR")
        response = self._get()
        content = response.content.decode()
        self.assertIn("var FALLBACK_COUNTRY = 'FR';", content)

    def test_cookie_settings_link_shown_when_enabled(self):
        self._set_usercentrics()
        response = self._get()
        self.assertContains(response, "wtr-cookie-settings")

    def test_cookie_settings_link_hidden_when_no_integration_entry(self):
        self.integration.integrations = []
        self.integration.save()
        response = self._get()
        self.assertNotContains(response, "wtr-cookie-settings")

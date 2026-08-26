"""
Tests for the Usercentrics consent snippet (wtrx/templates/wtrx/includes/
usercentrics_head.html), rendered via wtrx.context_processors.usercentrics.

Only the template's conditional structure is testable server-side here — the
runtime /cdn-cgi/trace fetch, its "loc=" parsing, the timeout race, and real
banner show/hide behavior all require a real Cloudflare-proxied environment
and are covered by manual QA instead (see AGENTS.md).
"""

from django.test import TestCase, override_settings
from wagtail.models import Page, Site

from wtrx.models import HomePage


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

    def _get(self):
        return self.client.get("/", HTTP_HOST=self.site.hostname)

    @override_settings(WTRX_USERCENTRICS_SETTINGS_ID="")
    def test_disabled_when_settings_id_blank(self):
        response = self._get()
        self.assertNotContains(response, "gtag(")
        self.assertNotContains(response, "UsercentricsConsent")

    @override_settings(WTRX_USERCENTRICS_SETTINGS_ID="test-id", WTRX_USERCENTRICS_COUNTRY="")
    def test_fetches_trace_when_no_country_override(self):
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

    @override_settings(WTRX_USERCENTRICS_SETTINGS_ID="test-id", WTRX_USERCENTRICS_COUNTRY="FR")
    def test_country_override_skips_trace_fetch(self):
        response = self._get()
        content = response.content.decode()
        self.assertIn("loadUsercentrics('FR')", content)
        self.assertNotIn("cdn-cgi/trace", content)

    @override_settings(
        WTRX_USERCENTRICS_SETTINGS_ID="test-id",
        WTRX_USERCENTRICS_VERSION="9.9.9",
        WTRX_USERCENTRICS_COUNTRY="",
    )
    def test_settings_id_and_version_interpolated(self):
        response = self._get()
        content = response.content.decode()
        self.assertIn("usercentrics-consent/9.9.9/usercentrics-consent.js", content)
        self.assertIn("settingsId: 'test-id'", content)

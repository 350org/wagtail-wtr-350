"""
Tests for context_processors.py.
"""

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase, override_settings

from wtrx.context_processors import google_sso

_GOOGLE_PROVIDERS = {
    "google": {
        "APP": {"client_id": "test-client-id", "secret": "test-secret", "key": ""},
    }
}
_NO_GOOGLE_PROVIDERS = {"google": {"APP": {}}}


class TestGoogleSsoContextProcessor(TestCase):
    """
    google_sso_only must never be True unless google_sso_enabled is also
    True — otherwise the login page could hide the password form with no
    way to sign in at all. See templates/wagtailadmin/login.html.
    """

    def _context(self):
        request = RequestFactory().get("/admin/login/")
        return google_sso(request)

    @override_settings(SOCIALACCOUNT_PROVIDERS=_NO_GOOGLE_PROVIDERS, WTRX_GOOGLE_SSO_ONLY=False)
    def test_google_not_configured(self):
        context = self._context()
        self.assertFalse(context["google_sso_enabled"])
        self.assertFalse(context["google_sso_only"])

    @override_settings(SOCIALACCOUNT_PROVIDERS=_GOOGLE_PROVIDERS, WTRX_GOOGLE_SSO_ONLY=False)
    def test_google_configured_only_off(self):
        context = self._context()
        self.assertTrue(context["google_sso_enabled"])
        self.assertFalse(context["google_sso_only"])

    @override_settings(SOCIALACCOUNT_PROVIDERS=_GOOGLE_PROVIDERS, WTRX_GOOGLE_SSO_ONLY=True)
    def test_google_configured_only_on(self):
        context = self._context()
        self.assertTrue(context["google_sso_enabled"])
        self.assertTrue(context["google_sso_only"])

    @override_settings(SOCIALACCOUNT_PROVIDERS=_NO_GOOGLE_PROVIDERS, WTRX_GOOGLE_SSO_ONLY=True)
    def test_only_flag_ignored_without_google_configured(self):
        context = self._context()
        self.assertFalse(context["google_sso_enabled"])
        self.assertFalse(context["google_sso_only"])


class TestLoginPageRendering(TestCase):
    """
    templates/wagtailadmin/login.html must hide the username/password
    fields and submit button only when google_sso_only is True, and always
    show the Google button whenever Google SSO is configured.
    """

    def setUp(self):
        # Wagtail's login view redirects an authenticated user away before
        # rendering the form, so these tests need an anonymous client.
        self.client.logout()

    @override_settings(SOCIALACCOUNT_PROVIDERS=_NO_GOOGLE_PROVIDERS, WTRX_GOOGLE_SSO_ONLY=False)
    def test_default_shows_password_form_only(self):
        response = self.client.get("/admin/login/")
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')
        self.assertNotContains(response, "Sign in with Google")

    @override_settings(SOCIALACCOUNT_PROVIDERS=_GOOGLE_PROVIDERS, WTRX_GOOGLE_SSO_ONLY=False)
    def test_google_enabled_shows_both(self):
        response = self.client.get("/admin/login/")
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')
        self.assertContains(response, "Sign in with Google")

    @override_settings(SOCIALACCOUNT_PROVIDERS=_GOOGLE_PROVIDERS, WTRX_GOOGLE_SSO_ONLY=True)
    def test_google_only_hides_password_form(self):
        response = self.client.get("/admin/login/")
        self.assertNotContains(response, 'name="username"')
        self.assertNotContains(response, 'name="password"')
        self.assertContains(response, "Sign in with Google")

    @override_settings(SOCIALACCOUNT_PROVIDERS=_GOOGLE_PROVIDERS, WTRX_GOOGLE_SSO_ONLY=True)
    def test_google_only_password_auth_still_works_server_side(self):
        """
        WTRX_GOOGLE_SSO_ONLY is a UI-only change — the form is hidden, but a
        direct POST with valid credentials must still authenticate. This is
        the documented fallback if Google SSO is ever misconfigured.
        """
        User.objects.create_superuser("admin", "admin@example.com", "password123")
        response = self.client.post(
            "/admin/login/", {"username": "admin", "password": "password123"}
        )
        self.assertRedirects(response, "/admin/", fetch_redirect_response=False)

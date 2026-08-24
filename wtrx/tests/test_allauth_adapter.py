"""
Tests for allauth_adapter.py.
"""

from unittest.mock import MagicMock

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from wtrx.allauth_adapter import DomainRestrictedSocialAccountAdapter, NoSignupAccountAdapter


class TestIsOpenForSignup(SimpleTestCase):
    """
    DomainRestrictedSocialAccountAdapter.is_open_for_signup must return True
    unconditionally — allauth's own default implementation delegates to the
    regular account adapter (NoSignupAccountAdapter, always False, since it
    exists only to close the username/password signup form), which without
    this override also blocks Google sign-in for any new account even though
    Google SSO is the intended account-creation path.
    """

    def test_returns_true(self):
        adapter = DomainRestrictedSocialAccountAdapter()
        request = RequestFactory().get("/accounts/google/login/callback/")
        self.assertTrue(adapter.is_open_for_signup(request, MagicMock()))


class TestPreSocialLogin(SimpleTestCase):
    def _adapter_and_sociallogin(self, email):
        adapter = DomainRestrictedSocialAccountAdapter()
        sociallogin = MagicMock()
        sociallogin.account.extra_data = {"email": email}
        return adapter, sociallogin

    @override_settings(WTRX_GOOGLE_SSO_DOMAIN="")
    def test_no_domain_configured_allows_any_email(self):
        adapter, sociallogin = self._adapter_and_sociallogin("anyone@example.com")
        request = RequestFactory().get("/")
        # Should not raise.
        adapter.pre_social_login(request, sociallogin)

    @override_settings(WTRX_GOOGLE_SSO_DOMAIN="withtheranks.com")
    def test_matching_domain_allowed(self):
        adapter, sociallogin = self._adapter_and_sociallogin("sukhada@withtheranks.com")
        request = RequestFactory().get("/")
        # Should not raise.
        adapter.pre_social_login(request, sociallogin)

    @override_settings(WTRX_GOOGLE_SSO_DOMAIN="withtheranks.com")
    def test_non_matching_domain_rejected(self):
        from allauth.core.exceptions import ImmediateHttpResponse

        adapter, sociallogin = self._adapter_and_sociallogin("someone@gmail.com")
        request = RequestFactory().get("/")
        request.session = {}

        # RequestFactory requests need message storage for messages.error to work.
        from django.contrib.messages.storage.fallback import FallbackStorage

        setattr(request, "_messages", FallbackStorage(request))

        with self.assertRaises(ImmediateHttpResponse):
            adapter.pre_social_login(request, sociallogin)


class TestPopulateUsername(SimpleTestCase):
    """
    NoSignupAccountAdapter.populate_username() must set the username to the
    email address, not allauth's default of slugifying the first name Google
    supplies — the username is what shows as the per-account label in an
    authenticator app during 2FA enrolment (django_otp reads
    user.get_username()), where a first-name-only label doesn't identify the
    account as clearly as the email does with several staff enrolled.
    """

    def test_sets_username_to_email(self):
        from django.contrib.auth.models import User

        adapter = NoSignupAccountAdapter()
        user = User(email="sukhada@withtheranks.com", first_name="Sukhada")
        request = RequestFactory().get("/accounts/google/login/callback/")

        adapter.populate_username(request, user)

        self.assertEqual(user.username, "sukhada@withtheranks.com")


class TestGetLoginRedirectUrl(SimpleTestCase):
    """
    NoSignupAccountAdapter.get_login_redirect_url() must send a user with
    Wagtail admin access to the admin home, and everyone else — most
    commonly a brand-new Google SSO signup with no permissions yet, since a
    superuser still has to add them to an Editor/Moderator group — to the
    "no CMS access" page. Without this override, allauth falls back to
    Django's default `/accounts/profile/`, which isn't a real page in this
    project and 404s.
    """

    def _adapter_and_request(self, *, has_admin_access):
        adapter = NoSignupAccountAdapter()
        request = RequestFactory().get("/accounts/google/login/callback/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user.has_perm.return_value = has_admin_access
        return adapter, request

    def test_admin_user_redirected_to_admin_home(self):
        adapter, request = self._adapter_and_request(has_admin_access=True)
        self.assertEqual(adapter.get_login_redirect_url(request), reverse("wagtailadmin_home"))

    def test_user_without_admin_access_redirected_to_no_cms_access(self):
        adapter, request = self._adapter_and_request(has_admin_access=False)
        self.assertEqual(adapter.get_login_redirect_url(request), reverse("no_cms_access"))

    def test_checks_wagtailadmin_access_admin_permission(self):
        adapter, request = self._adapter_and_request(has_admin_access=True)
        adapter.get_login_redirect_url(request)
        request.user.has_perm.assert_called_once_with("wagtailadmin.access_admin")

"""
Tests for wtrx/forms.py — the wagtail_2fa DeviceForm patch for SSO users.
"""

from django.contrib.auth.models import User
from django.test import RequestFactory, SimpleTestCase

from wtrx.forms import SSOAwareDeviceForm


class TestSSOAwareDeviceForm(SimpleTestCase):
    """
    wagtail_2fa.forms.DeviceForm always requires the user's current
    password. SSOAwareDeviceForm must drop that field for a user with no
    usable password (every Google SSO account — see allauth_adapter.py) —
    Django's authenticate() can never succeed for them, so keeping the
    field would permanently block 2FA setup.
    """

    def _request_for(self, user):
        request = RequestFactory().get("/admin/2fa/devices/new")
        request.user = user
        return request

    def test_password_field_dropped_for_unusable_password_user(self):
        user = User(username="sso-user")
        user.set_unusable_password()
        form = SSOAwareDeviceForm(self._request_for(user), data={})
        self.assertNotIn("password", form.fields)

    def test_password_field_kept_for_usable_password_user(self):
        user = User(username="password-user")
        user.set_password("correct horse battery staple")
        form = SSOAwareDeviceForm(self._request_for(user), data={})
        self.assertIn("password", form.fields)

    def test_dropped_field_not_validated(self):
        """
        With the field gone, clean_password() must never run — otherwise an
        SSO user could never submit the form at all, regardless of what
        they type (or don't type) into a password field they can't see.
        """
        user = User(username="sso-user-2")
        user.set_unusable_password()
        form = SSOAwareDeviceForm(
            self._request_for(user),
            data={"name": "My phone", "otp_token": "123456"},
        )
        form.is_valid()
        self.assertNotIn("password", form.errors)


class TestPatchWagtailTwoFactorDeviceForm(SimpleTestCase):
    """
    WtrxConfig.ready() calls patch_wagtail_2fa_device_form() on startup —
    by the time any test runs, wagtail_2fa's device views should already
    be using SSOAwareDeviceForm instead of their own DeviceForm.
    """

    def test_device_create_view_uses_sso_aware_form(self):
        from wagtail_2fa import views as wagtail_2fa_views

        self.assertIs(wagtail_2fa_views.DeviceCreateView.form_class, SSOAwareDeviceForm)

    def test_device_update_view_uses_sso_aware_form(self):
        from wagtail_2fa import views as wagtail_2fa_views

        self.assertIs(wagtail_2fa_views.DeviceUpdateView.form_class, SSOAwareDeviceForm)

"""
Small patches to third-party admin forms.

See patch_wagtail_2fa_device_form(), called from WtrxConfig.ready().
"""

from wagtail_2fa import forms as wagtail_2fa_forms
from wagtail_2fa import views as wagtail_2fa_views


class SSOAwareDeviceForm(wagtail_2fa_forms.DeviceForm):
    """
    wagtail_2fa.forms.DeviceForm always asks for the user's current
    password as an extra check before creating/updating a 2FA device,
    via clean_password()'s call to Django's authenticate().

    Google SSO users have no password at all — allauth's
    DefaultSocialAccountAdapter.save_user() calls set_unusable_password()
    for every account it creates (see allauth_adapter.py) — so
    authenticate() can never succeed for them, and the password field
    would permanently block them from ever completing 2FA setup.

    For a user with no usable password, drop the field entirely rather
    than trying to validate it: the template renders `{% for field in
    form %}` generically (wagtail_2fa/device_form.html), so removing it
    from self.fields also removes it from the page, and Django's
    _clean_fields() only calls clean_<name>() for fields still present, so
    clean_password() is simply never reached. They've already proven their
    identity via SSO to get this far, so the extra password check is
    redundant for them anyway — it exists to stop someone who found an
    already-logged-in session from silently enrolling their own 2FA
    device, and SSO users have no separate password an attacker could
    lack.
    """

    def __init__(self, request, **kwargs):
        super().__init__(request, **kwargs)
        if not request.user.has_usable_password():
            del self.fields["password"]


def patch_wagtail_2fa_device_form():
    """Point wagtail_2fa's device views at SSOAwareDeviceForm instead of
    its own DeviceForm. Called from WtrxConfig.ready()."""
    wagtail_2fa_views.DeviceCreateView.form_class = SSOAwareDeviceForm
    wagtail_2fa_views.DeviceUpdateView.form_class = SSOAwareDeviceForm

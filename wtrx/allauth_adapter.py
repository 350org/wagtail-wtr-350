"""
django-allauth adapter for Google SSO.

Enforces the org-domain restriction server-side. SOCIALACCOUNT_PROVIDERS'
google.AUTH_PARAMS.hd only hints Google's account picker to prefer that
domain — it is not a security boundary, since a user can still complete the
OAuth flow with an out-of-domain account. This adapter rejects the login
after the fact, based on the verified email address Google returns.
"""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect


class DomainRestrictedSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        allowed_domain = getattr(settings, "WTRX_GOOGLE_SSO_DOMAIN", "")
        if not allowed_domain:
            return

        email = (sociallogin.account.extra_data.get("email") or "").lower()
        if not email.endswith(f"@{allowed_domain.lower()}"):
            messages.error(
                request,
                f"Sign-in restricted to @{allowed_domain} accounts.",
            )
            raise ImmediateHttpResponse(redirect("wagtailadmin_login"))

    def is_open_for_signup(self, request, sociallogin):
        # DefaultSocialAccountAdapter's own is_open_for_signup delegates to
        # the *regular* account adapter (get_account_adapter(request)
        # .is_open_for_signup(request)) — NoSignupAccountAdapter, which is
        # always False since it exists to close the username/password signup
        # form. Left un-overridden, that same False also blocks Google
        # sign-in for any not-yet-existing account, even though Google SSO is
        # the intended account-creation path (SOCIALACCOUNT_AUTO_SIGNUP).
        # The domain restriction above still runs first and can reject the
        # login before this is ever reached.
        return True


class NoSignupAccountAdapter(DefaultAccountAdapter):
    """Disable allauth's own username/password signup form — accounts are
    either created via Google SSO (see DomainRestrictedSocialAccountAdapter
    above) or by a superuser in the Wagtail Users admin."""

    def is_open_for_signup(self, request) -> bool:
        return False

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
from django.urls import reverse


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

    def populate_username(self, request, user):
        """
        Use the Google-verified email as the username, rather than allauth's
        default of slugifying the first name it got from Google. This
        account's username is what shows as the per-account label next to
        OTP_TOTP_ISSUER in every staff member's authenticator app during 2FA
        enrolment (django_otp.TOTPDevice.config_url reads user.get_username())
        — a first-name-only label like "sukhada" doesn't identify the
        account as clearly as the full email does, especially with several
        staff enrolled.
        """
        from allauth.account.utils import user_email, user_username

        user_username(user, user_email(user))

    def get_login_redirect_url(self, request):
        """
        Where to send a user immediately after login, when they didn't
        arrive via an explicit `?next=` (allauth checks that first and
        only falls back to this). Without this override that fallback is
        Django's global default, `/accounts/profile/` — not a real page
        here, so it 404s. This is the common case for a brand-new Google
        SSO signup: they have no admin permissions yet (a superuser has to
        add them to an Editor/Moderator group first), so send them
        somewhere that explains that instead of a broken page; a user who
        already has admin access goes to the admin home instead.
        """
        if request.user.is_authenticated and request.user.has_perm(
            "wagtailadmin.access_admin"
        ):
            return reverse("wagtailadmin_home")
        return reverse("no_cms_access")

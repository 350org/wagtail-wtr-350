"""Template context processors for wtrx."""

from django.conf import settings


def usercentrics(request):
    """
    Expose the Usercentrics consent-management config to every template.

    ``usercentrics_settings_id`` empty → the consent snippet is not rendered
    (used to disable it in local development). See wtrx/templates/wtrx/includes/
    usercentrics_head.html.
    """
    return {
        "usercentrics_settings_id": getattr(
            settings, "WTRX_USERCENTRICS_SETTINGS_ID", ""
        ),
        "usercentrics_version": getattr(
            settings, "WTRX_USERCENTRICS_VERSION", "1.1.4"
        ),
        "usercentrics_country": getattr(settings, "WTRX_USERCENTRICS_COUNTRY", ""),
    }


def google_sso(request):
    """
    Whether Google SSO is fully configured (client ID present), used by the
    wagtailadmin/login.html override to show/hide the "Sign in with Google"
    button — clicking it with no client ID configured would just fail against
    Google with an invalid_client error.

    ``google_sso_only`` additionally hides the username/password fields and
    submit button, controlled by the WTRX_GOOGLE_SSO_ONLY env var — it's
    only ever True alongside ``google_sso_enabled``, so a site can never end
    up with the password form hidden and no way to sign in at all.
    """
    google_app = settings.SOCIALACCOUNT_PROVIDERS.get("google", {}).get("APP", {})
    google_sso_enabled = bool(google_app.get("client_id"))
    return {
        "google_sso_enabled": google_sso_enabled,
        "google_sso_only": google_sso_enabled
        and getattr(settings, "WTRX_GOOGLE_SSO_ONLY", False),
    }

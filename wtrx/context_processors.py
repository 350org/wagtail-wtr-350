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
    """
    google_app = settings.SOCIALACCOUNT_PROVIDERS.get("google", {}).get("APP", {})
    return {"google_sso_enabled": bool(google_app.get("client_id"))}

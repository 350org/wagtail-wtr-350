"""Template context processors for wtrx."""

from django.conf import settings


def usercentrics(request):
    """
    Expose the Usercentrics consent-management config to every template.

    ``usercentrics_settings_id`` empty → the consent snippet is not rendered
    (used to disable it in local development). See wtrx/templates/wtrx/includes/
    usercentrics_head.html and the Usercentrics integration doc.
    """
    return {
        "usercentrics_settings_id": getattr(
            settings, "WTRX_USERCENTRICS_SETTINGS_ID", ""
        ),
        "usercentrics_version": getattr(
            settings, "WTRX_USERCENTRICS_VERSION", "1.1.4"
        ),
    }

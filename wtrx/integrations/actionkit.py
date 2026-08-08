"""
ActionKit REST API integration — server-side signup forwarding.

This module is intentionally free of Django model imports so it stays an
extractable, unit-testable seam (see PLAN.md "platform forwarding"). The caller
(FormPage.process_form_submission) is responsible for reading configuration and
for swallowing/logging errors so a failed forward never blocks the user.

ActionKit's "action" endpoint records a user taking an action on a named page:
    POST https://<hostname>/rest/v1/action/
    Auth: HTTP Basic (API username + password)
    Body (JSON): {"page": "<page short name>", "email": "...", <user fields>}
Standard user fields (first_name, last_name, zip, phone, city, state, address1)
are passed at the top level; anything unrecognised is sent as an ActionKit
custom user field using the ``user_<name>`` convention.

ActionKit's public page endpoint also serves an embeddable HTML fragment of a
page's own form (see ``fetch_embed_form_html``), used by SignupActionKitBlock
to auto-render whatever fields an ActionKit page is configured with, given
just its short name:
    GET https://<hostname>/act/<page short name>?form_only=1&abs_urls=1
No auth required — this is the same markup ActionKit serves to anonymous
visitors of the hosted page, just without the surrounding site chrome.
"""

import requests
from django.utils.translation import gettext_lazy as _
from wagtail.blocks import BooleanBlock, CharBlock, StructBlock

from wtrx.integrations.registry import IntegrationType, register_integration


class ActionKitError(Exception):
    """Raised when ActionKit is misconfigured or returns a non-success response."""


# Field names ActionKit's own hosted forms already post under the
# ``action_<name>`` convention — passed through verbatim (not re-prefixed
# with ``user_``) so they land on the actual Action-model fields ActionKit
# uses for campaign-attribution reporting, not as meaningless custom fields.
ACTIONKIT_NATIVE_FIELDS = {
    "action_utm_source",
    "action_utm_medium",
    "action_utm_campaign",
    "action_utm_term",
    "action_utm_content",
}


# Wagtail form fields arrive keyed by their ``clean_name`` (a slug of the field
# label, e.g. "Email address" -> "email_address"). These heuristics map the
# common signup fields onto ActionKit's field names.
def map_form_fields(cleaned_data):
    """
    Map a Wagtail form's ``cleaned_data`` to ActionKit action fields.

    Returns a dict suitable for merging into the ActionKit request body. Blank
    values are dropped. ACTIONKIT_NATIVE_FIELDS pass through as-is; other
    unrecognised fields become ``user_<clean_name>`` custom fields. If no email
    is present the caller should skip forwarding — ActionKit requires an email
    to identify the user.
    """
    result = {}
    name_split = None

    for raw_key, value in cleaned_data.items():
        if value in (None, ""):
            continue
        value = str(value).strip()
        if not value:
            continue
        key = raw_key.lower()

        if key in ACTIONKIT_NATIVE_FIELDS:
            result[key] = value
        elif "email" in key:
            result.setdefault("email", value)
        elif ("first" in key and "name" in key) or key in ("firstname", "first_name"):
            result["first_name"] = value
        elif ("last" in key and "name" in key) or key in (
            "lastname",
            "last_name",
            "surname",
        ):
            result["last_name"] = value
        elif key in ("name", "full_name", "fullname", "your_name"):
            parts = value.split()
            if parts:
                name_split = (parts[0], " ".join(parts[1:]))
        elif "zip" in key or "postal" in key:
            result["zip"] = value
        elif "phone" in key or "mobile" in key or "cell" in key:
            result["phone"] = value
        elif "city" in key:
            result["city"] = value
        elif key == "state" or "province" in key:
            result["state"] = value
        elif "address" in key or "street" in key:
            result["address1"] = value
        else:
            result[f"user_{raw_key}"] = value

    # A single "name" field fills first/last only where explicit fields did not.
    if name_split:
        result.setdefault("first_name", name_split[0])
        if name_split[1]:
            result.setdefault("last_name", name_split[1])

    return result


def base_url(hostname):
    """Normalise a hostname or full URL to a scheme-qualified base with no trailing slash."""
    host = (hostname or "").strip().rstrip("/")
    if host.startswith(("http://", "https://")):
        return host
    return f"https://{host}"


def submit_action(hostname, username, password, page, fields, timeout=5):
    """
    POST an action to ActionKit's REST API.

    ``fields`` is the mapped dict from :func:`map_form_fields` (must contain
    ``email``). Returns None on success (HTTP 2xx); raises :class:`ActionKitError`
    on missing configuration or any non-2xx response. Network errors from
    ``requests`` propagate to the caller, which is expected to catch and log them.
    """
    if not (hostname and username and page):
        raise ActionKitError(
            "ActionKit hostname, API username, and page name are all required."
        )

    url = f"{base_url(hostname)}/rest/v1/action/"
    payload = {"page": page, **fields}

    response = requests.post(
        url,
        json=payload,
        auth=(username, password),
        headers={"Accept": "application/json"},
        timeout=timeout,
    )

    if not 200 <= response.status_code < 300:
        raise ActionKitError(
            f"ActionKit returned HTTP {response.status_code}: {response.text[:500]}"
        )


def fetch_embed_form_html(hostname, short_form_id, timeout=5):
    """
    Fetch the auto-rendered HTML fragment for an ActionKit page's form.

    Uses ActionKit's ``form_only=1&abs_urls=1`` query params, which return just
    the page's title/description/form markup with no site chrome (header, nav,
    footer, or ActionKit's own stylesheet) — safe to splice into another page's
    HTML and restyle with our own CSS. Whatever fields that ActionKit page is
    actually configured with come along automatically; nothing here needs to
    know what they are.

    Returns the raw HTML fragment (str) on success. Raises :class:`ActionKitError`
    on missing configuration or any non-2xx response. Network errors from
    ``requests`` propagate to the caller. Callers are expected to cache the
    result — this hits ActionKit's live server on every call.
    """
    if not (hostname and short_form_id):
        raise ActionKitError("ActionKit hostname and short form ID are required.")

    url = f"{base_url(hostname)}/act/{short_form_id}"

    response = requests.get(
        url,
        params={"form_only": 1, "abs_urls": 1},
        timeout=timeout,
    )

    if not 200 <= response.status_code < 300:
        raise ActionKitError(
            f"ActionKit returned HTTP {response.status_code}: {response.text[:500]}"
        )

    return response.text


# ---------------------------------------------------------------------------
# Integration registration
# ---------------------------------------------------------------------------


class ActionKitConfigBlock(StructBlock):
    """Per-site ActionKit configuration, added as an entry in Settings > Integrations."""

    enabled = BooleanBlock(
        required=False,
        default=True,
        label=_("Enabled"),
        help_text=_("Uncheck to temporarily disable ActionKit without removing its configuration."),
    )
    hostname = CharBlock(
        label=_("ActionKit hostname"),
        help_text=_(
            "Your ActionKit instance hostname, e.g. 'myorg.actionkit.com' "
            "(no scheme or trailing slash needed)."
        ),
    )
    api_username = CharBlock(
        label=_("ActionKit API username"),
        help_text=_("The ActionKit REST API username used for HTTP Basic auth."),
    )
    api_password = CharBlock(
        required=False,
        label=_("ActionKit API password"),
        help_text=_(
            "The ActionKit REST API password. In production, prefer the "
            "WTRX_ACTIONKIT_API_PASSWORD environment variable, which overrides "
            "this value so the secret is not stored in the database."
        ),
    )

    class Meta:
        icon = "cogs"
        label = _("ActionKit")


register_integration(
    IntegrationType(
        slug="actionkit",
        label=_("ActionKit"),
        category="signup",
        content_block_names=("signup_actionkit",),
    )
)

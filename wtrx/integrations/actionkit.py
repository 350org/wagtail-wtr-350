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
"""

import requests


class ActionKitError(Exception):
    """Raised when ActionKit is misconfigured or returns a non-success response."""


# Wagtail form fields arrive keyed by their ``clean_name`` (a slug of the field
# label, e.g. "Email address" -> "email_address"). These heuristics map the
# common signup fields onto ActionKit's field names.
def map_form_fields(cleaned_data):
    """
    Map a Wagtail form's ``cleaned_data`` to ActionKit action fields.

    Returns a dict suitable for merging into the ActionKit request body. Blank
    values are dropped. Unrecognised fields become ``user_<clean_name>`` custom
    fields. If no email is present the caller should skip forwarding — ActionKit
    requires an email to identify the user.
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

        if "email" in key:
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


def _base_url(hostname):
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

    url = f"{_base_url(hostname)}/rest/v1/action/"
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

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

import logging
import re
from html.parser import HTMLParser

import requests
from bs4 import BeautifulSoup
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _
from wagtail.blocks import BooleanBlock, CharBlock, StructBlock

from wtrx.integrations.registry import IntegrationType, register_integration

logger = logging.getLogger(__name__)


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


# ActionKit stamps an Action's "source" with its own "restful_api" default
# for anything submitted through this endpoint (as opposed to a browser POST
# straight to an ActionKit-hosted page, which it tags "website") -- both of
# our submission paths (FormPage forwarding, SignupActionKitBlock's inline
# endpoint) are really website visitors filling in our own embedded forms,
# so a request-level "source" isn't collected to make this configurable.
# ``fields`` is spread after this default, so a source ever present there
# (there isn't one today -- map_form_fields has no "source" mapping) would
# still win.
DEFAULT_ACTION_SOURCE = "website"


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
    payload = {"page": page, "source": DEFAULT_ACTION_SOURCE, **fields}

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

    return _fix_country_label_for_attribute(_make_recaptcha_async(response.text))


# ActionKit's fetched fragment includes its own <script
# src="https://www.google.com/recaptcha/api.js"></script> tag with no
# async/defer -- fine on ActionKit's own hosted page, but once spliced into
# our page via {{ form_html|safe }} it blocks HTML parsing exactly like a
# first-party blocking script would (confirmed live via PageSpeed Insights
# flagging recaptcha/api.js as a render-blocking resource, 750ms of it).
# Google's own docs recommend loading api.js with async/defer, and recaptcha
# only ever renders in response to an explicit callback/onload, not at parse
# time, so this is safe.
_RECAPTCHA_SCRIPT_RE = re.compile(
    r'<script\s+src="https://www\.google\.com/recaptcha/api\.js"\s*>'
)


def _make_recaptcha_async(html):
    return _RECAPTCHA_SCRIPT_RE.sub(
        '<script src="https://www.google.com/recaptcha/api.js" async>', html
    )


# ActionKit's own country <select> renders with id="country" (no "id_"
# prefix, unlike every other field -- e.g. email's input carries
# id="id_email"), but its <label> still points at for="id_country" -- a
# genuine for/id mismatch in ActionKit's own markup, confirmed live via a
# direct fetch of the raw fragment (grepping every <label for="..."> against
# every id="..." in the same response: id_email resolves, id_country does
# not). Browsers/screen readers match `for` by exact id, so this leaves the
# select with no accessible name -- confirmed via PageSpeed Insights'
# "Select elements do not have associated label elements" audit. Safe to
# rewrite: static_src/js/components/actionkit-country-prefill.js selects
# this field by `select[name="country"]`, never by id.
_COUNTRY_LABEL_FOR_RE = re.compile(r'<label for="id_country">')


def _fix_country_label_for_attribute(html):
    return _COUNTRY_LABEL_FOR_RE.sub('<label for="country">', html)


# 350's ActionKit template puts a page's intro copy in <div id="action-header">,
# a sibling of <form id="action-form"> inside the outer #action-lead section:
# the pretitle, the title, the description (which is where an editor's
# embedded logo lives), and on a petition, a "View the full petition text"
# link whose target (#petition-text) sits in a no-JS box beside it. On
# ActionKit and WordPress this is the page's left-hand column. Our blocks
# render their own left-hand column, so the header is lifted out of the
# fragment and handed to the template as data instead of being hidden.
_ACTION_HEADER_START_RE = re.compile(r'<div\b[^>]*\bid="action-header"[^>]*>')
_ACTION_FORM_START_RE = re.compile(r'<form\b[^>]*\bid="action-form"')


class _ElementEndFinder(HTMLParser):
    """
    Records where the element opened at the very start of the fed HTML closes.

    A real parser rather than counting ``<div`` substrings, because the
    description is editor-authored HTML from ActionKit's page editor and can
    carry comments or embeds that a substring count would miscount.
    """

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.tag = None
        self.depth = 0
        self.end_pos = None  # (line, column) of the matching closing tag

    def handle_starttag(self, tag, attrs):
        if self.end_pos is not None:
            return
        if self.tag is None:
            self.tag = tag
        if tag == self.tag:
            self.depth += 1

    def handle_endtag(self, tag):
        if self.end_pos is not None or tag != self.tag:
            return
        self.depth -= 1
        if self.depth == 0:
            self.end_pos = self.getpos()


def _element_end_offset(html):
    """Offset just past the closing tag of the element ``html`` starts with, or None."""
    finder = _ElementEndFinder()
    finder.feed(html)
    if finder.end_pos is None:
        return None
    line, column = finder.end_pos
    line_start = 0
    for _ in range(line - 1):
        line_start = html.index("\n", line_start) + 1
    close_tag_end = html.find(">", line_start + column)
    return None if close_tag_end == -1 else close_tag_end + 1


def split_action_header(html):
    """
    Lift ActionKit's ``#action-header`` intro out of a fetched form fragment.

    Returns ``(intro, remaining_html)``. ``intro`` is a dict of the header's
    parts — ``pretitle`` and ``title`` (plain text), ``description_html``,
    and, on a petition, ``petition_html`` plus ``petition_link_text`` for the
    "view the full petition text" modal — or None when the fragment has no
    header (a different ActionKit template, or a fetch that failed). The
    header is removed from ``remaining_html`` so its ids aren't duplicated
    on the page; the form itself is untouched byte-for-byte, since its
    inline scripts are sensitive to being re-serialised.
    """
    if not html:
        return None, html
    header_start = _ACTION_HEADER_START_RE.search(html)
    if not header_start:
        return None, html
    form_start = _ACTION_FORM_START_RE.search(html, header_start.start())
    region_end = form_start.start() if form_start else len(html)
    header_length = _element_end_offset(html[header_start.start():region_end])
    if header_length is None:
        return None, html
    header_end = header_start.start() + header_length

    header = BeautifulSoup(html[header_start.start():header_end], "html.parser")

    # YouTube refuses to play an embed that arrives with no referrer ("Error
    # 153"), and this site sends none cross-origin: Django's default
    # SECURE_REFERRER_POLICY is "same-origin". Petition text often embeds a
    # video, so each iframe gets the browser-default policy back for itself.
    for iframe in header.find_all("iframe"):
        iframe["referrerpolicy"] = "strict-origin-when-cross-origin"

    def text_of(selector):
        element = header.select_one(selector)
        return element.get_text(" ", strip=True) if element else ""

    petition_box = header.select_one("#petition-text")
    petition_link = header.select_one("a.js-modal")
    petition_html = petition_box.decode_contents().strip() if petition_box else ""

    description = header.select_one("#action-description-text") or header.select_one(
        "#action-description"
    )
    description_html = ""
    if description:
        # The petition link and its no-JS box sit inside #action-description
        # on templates without an #action-description-text wrapper; either
        # way they're rendered separately, as a button and a <dialog>.
        for element in description.select(".petition-text-link, .js-hidden, meta"):
            element.decompose()
        description_html = description.decode_contents().strip()

    intro = {
        "pretitle": text_of("#action-pretitle"),
        "title": text_of("#action-title"),
        "description_html": description_html,
        "petition_html": petition_html,
        "petition_link_text": (
            petition_link.get_text(" ", strip=True) if petition_link and petition_html else ""
        ),
    }
    remaining_html = html[: header_start.start()] + html[header_end:]
    return (intro if any(intro.values()) else None), remaining_html


# Shared by every caller that auto-renders a fetched ActionKit form
# (SignupActionKitBlock, the footer newsletter signup) so they hit the same
# cache key format and retry window instead of each keeping its own copy of
# this logic — the same ActionKit page fetched from two call sites should
# still only hit ActionKit's live server at this one shared rate.
EMBED_FORM_SUCCESS_CACHE_TIMEOUT = 60 * 15  # 15 minutes
EMBED_FORM_FAILURE_CACHE_TIMEOUT = 60  # retry a broken/misconfigured page once a minute
_EMBED_FORM_FETCH_FAILED = "__actionkit_embed_fetch_failed__"


def fetch_and_cache_embed_form_html(hostname, short_form_id):
    """
    Cached wrapper around fetch_embed_form_html().

    Returns the cached (or freshly fetched) form fragment, or None if the
    fetch failed (also cached, briefly, so a broken/misconfigured page
    doesn't get hit on every render). The failure itself is logged — a
    silent None here previously left no way to tell a timeout apart from a
    bad short_form_id or a genuine ActionKit outage from production logs.
    """
    cache_key = f"wtrx:actionkit_embed:{hostname}:{short_form_id}"
    cached = cache.get(cache_key)
    if cached == _EMBED_FORM_FETCH_FAILED:
        return None
    if cached is not None:
        return cached

    try:
        html = fetch_embed_form_html(hostname, short_form_id)
    except (ActionKitError, requests.RequestException) as exc:
        logger.warning(
            "ActionKit embed form fetch failed for %s/%s: %s", hostname, short_form_id, exc
        )
        cache.set(cache_key, _EMBED_FORM_FETCH_FAILED, EMBED_FORM_FAILURE_CACHE_TIMEOUT)
        return None

    cache.set(cache_key, html, EMBED_FORM_SUCCESS_CACHE_TIMEOUT)
    return html


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

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
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _
from wagtail.blocks import BooleanBlock, CharBlock, StructBlock

from wtrx.integrations.registry import IntegrationType, register_integration

logger = logging.getLogger(__name__)


class ActionKitError(Exception):
    """Raised when ActionKit is misconfigured or returns a non-success response."""

    def __init__(self, message="", status_code=None):
        super().__init__(message)
        #: The HTTP status ActionKit returned, when the error is a response.
        self.status_code = status_code


# ActionKit's convention for a custom *action* field: anything its forms post
# as ``action_<name>`` (the UTM attribution fields, a petition's
# ``action_comment``, ...) is stored on the action itself, and needs no
# definition in ActionKit first. Passed through verbatim: re-prefixed as
# ``user_action_<name>`` it would be a custom *user* field, which ActionKit
# rejects the whole submission for unless one by that name exists.
ACTIONKIT_ACTION_FIELD_PREFIX = "action_"


# Wagtail form fields arrive keyed by their ``clean_name`` (a slug of the field
# label, e.g. "Email address" -> "email_address"). These heuristics map the
# common signup fields onto ActionKit's field names.
def map_form_fields(cleaned_data):
    """
    Map a Wagtail form's ``cleaned_data`` to ActionKit action fields.

    Returns a dict suitable for merging into the ActionKit request body. Blank
    values are dropped. ``action_<name>`` fields pass through as-is; other
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

        if key.startswith(ACTIONKIT_ACTION_FIELD_PREFIX):
            result[raw_key] = value
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
        # ActionKit core user fields, posted under their own names by its
        # embedded form. Sent as user_country/user_region they would land as
        # custom fields and a page that requires country would reject the
        # signup for any user without one on file.
        elif key in ("country", "region"):
            result[key] = value
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
# endpoint) are really website visitors filling in our own embedded forms.
# ``fields`` is spread after this default, so a ``?source=`` from the page
# URL (forwarded by the inline endpoint, see views.py) wins over it.
DEFAULT_ACTION_SOURCE = "website"


# ActionKit's response when a submission carries a ``user_<name>`` field that
# isn't one of its allowed custom user fields. It names the fields without
# their prefix: "The user field action_comment is not allowed." / "The user
# fields a,b are not allowed."
_REJECTED_USER_FIELDS_RE = re.compile(r"The user fields? ([\w\-, ]+?) (?:is|are) not allowed")


def rejected_user_fields(response_text):
    """Return the custom user field names an ActionKit error says it won't accept."""
    match = _REJECTED_USER_FIELDS_RE.search(response_text or "")
    if not match:
        return []
    return [name.strip() for name in match.group(1).split(",") if name.strip()]


def submit_action(hostname, username, password, page, fields, timeout=5):
    """
    POST an action to ActionKit's REST API.

    ``fields`` is the dict to send (must contain ``email``). Returns
    ActionKit's JSON response body as a dict on success (HTTP 2xx; empty when
    the body isn't a JSON object); raises :class:`ActionKitError` on missing
    configuration or any non-2xx response. Network errors from ``requests``
    propagate to the caller, which is expected to catch and log them.

    ActionKit refuses a whole submission over one ``user_<name>`` field it has
    no custom user field for. When that is the reason given, the named fields
    are dropped and the action is sent once more, so a stray field costs that
    field and not the signup.
    """
    if not (hostname and username and page):
        raise ActionKitError(
            "ActionKit hostname, API username, and page name are all required."
        )

    url = f"{base_url(hostname)}/rest/v1/action/"
    payload = {"page": page, "source": DEFAULT_ACTION_SOURCE, **fields}

    def post():
        return requests.post(
            url,
            json=payload,
            auth=(username, password),
            headers={"Accept": "application/json"},
            timeout=timeout,
        )

    response = post()

    if response.status_code == 400:
        dropped = [
            key
            for key in (f"user_{name}" for name in rejected_user_fields(response.text))
            if key in payload
        ]
        if dropped:
            logger.warning(
                "ActionKit page %s does not accept the user field(s) %s; resubmitting without them.",
                page,
                ", ".join(dropped),
            )
            for key in dropped:
                del payload[key]
            response = post()

    if not 200 <= response.status_code < 300:
        raise ActionKitError(
            f"ActionKit returned HTTP {response.status_code}: {response.text[:500]}",
            status_code=response.status_code,
        )

    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def signup_redirect(hostname, page, action):
    """
    Where a signup should send the visitor next, per the ActionKit page's own
    "redirect to" (after-action) setting.

    ``action`` is :func:`submit_action`'s return value, whose ``redirect_url``
    is that setting with ``action_id``/``akid`` already appended. Returns
    ``(url, is_actionkit, is_default)``, or ``None`` when there is nothing to
    follow:

    - ActionKit gives every page a redirect, defaulting to its own
      ``/cms/thanks/<page>``. That default is what a page has when nobody set
      one, so it is flagged ``is_default`` and is only a last resort: the
      block's own thank-you handling (donation checkout, success message)
      runs first, and the caller follows it only when the block has neither.
    - ``is_actionkit`` is True when the destination is on the ActionKit host.
      The caller uses it to decide who records the conversion: ActionKit's
      thank-you page does, from ``action_id``, so our own tracking event must
      not also fire.
    """
    raw = action.get("redirect_url") if isinstance(action, dict) else None
    if not raw or not isinstance(raw, str):
        return None

    ak_base = base_url(hostname)
    url = urljoin(f"{ak_base}/", raw.strip())
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None

    is_actionkit = parts.netloc.lower() == urlsplit(ak_base).netloc.lower()
    is_default = is_actionkit and parts.path.rstrip("/") == f"/cms/thanks/{page}"
    return url, is_actionkit, is_default


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
            f"ActionKit returned HTTP {response.status_code}: {response.text[:500]}",
            status_code=response.status_code,
        )

    return _strip_submit_arrow(_fix_country_label_for_attribute(_make_recaptcha_async(response.text)))


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


# Some ActionKit pages type a trailing arrow into the submit label ("Junte-se
# a nós →"), while every embed variant already draws its own arrow icon on
# the button (main.css/theme.css), so the label ends up with two. Strip a
# trailing arrow character or entity from a submit <button>'s text or an
# <input type="submit">'s value; the icon stays the only arrow.
_ARROW = r"(?:\s|&nbsp;)*(?:[\u2192\u2794\u279c\u27a1\u00bb]|&rarr;|&#8594;|&#x2192;|&raquo;)(?:\s|&nbsp;)*"
_SUBMIT_BUTTON_ARROW_RE = re.compile(
    r"(<button\b[^>]*\btype=\"submit\"[^>]*>(?:(?!</button>).)*?)" + _ARROW + r"(</button>)",
    re.DOTALL | re.IGNORECASE,
)
_SUBMIT_INPUT_ARROW_RE = re.compile(
    r"(<input\b[^>]*\btype=\"submit\"[^>]*\bvalue=\"[^\"]*?)" + _ARROW + r"(\")",
    re.IGNORECASE,
)


def _strip_submit_arrow(html):
    html = _SUBMIT_BUTTON_ARROW_RE.sub(r"\1\2", html)
    return _SUBMIT_INPUT_ARROW_RE.sub(r"\1\2", html)


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


# Every ActionKit embed fetches the same fragment, which hardcodes its ids
# (action-form, unknown_user, id_email, ak-errors, ...), so a page with more
# than one embed — the home page has three: hero, panel and footer — repeats
# each of them. uniquify_form_ids() gives every embed after the first its own
# copies. The first keeps AK's ids, so the fragment's own inline scripts,
# which look elements up page-globally (getElementById("id_email"),
# jQuery("#unknown_user ...")), keep resolving exactly what they always did:
# duplicate ids only ever resolved to the first embed anyway. The fragment
# also repeats one id inside itself (two <span id="known_user_name">s in its
# "Hi ___ / Not ___?" box), so a repeat within one embed is renamed too, the
# first embed included.
#
# Renamed elements also get data-ak-id="<original>", which is what our own
# CSS and _actionkit_form.html's script select on alongside the bare id.
#
# Regex rather than BeautifulSoup, and only outside <script>/<style>, for the
# same reason split_action_header() leaves the form alone: the inline scripts
# are sensitive to being re-serialised.
_RAW_TEXT_ELEMENT_RE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[a-zA-Z][^>]*>")
_ID_ATTR_RE = re.compile(r'(\sid=")([^"]+)(")')
_ID_REF_RES = (
    re.compile(r'(<label\b[^>]*\sfor=")([^"]+)(")', re.IGNORECASE),
    re.compile(r'(\s(?:aria-labelledby|aria-describedby|aria-controls)=")([^"]+)(")'),
    re.compile(r'(\shref="#)([^"]+)(")'),
)

#: Request attribute counting the ActionKit embeds rendered so far.
_FORM_COUNT_ATTR = "_wtrx_actionkit_form_count"


def uniquify_form_ids(html, request):
    """
    Return ``html`` with its ids made unique for this request (see above).

    Later embeds get ``--2``, ``--3``, ... appended to every id, with
    ``<label for>``, ``href="#..."`` and ``aria-*`` id references inside the
    fragment renamed to match; a repeat of an id within one embed also gets
    ``-2``, ``-3``, ... (references keep pointing at its first occurrence).
    Without a request there is nothing to count against, so the html is
    returned as-is.
    """
    if not html or request is None:
        return html
    count = getattr(request, _FORM_COUNT_ATTR, 0) + 1
    setattr(request, _FORM_COUNT_ATTR, count)
    suffix = f"--{count}" if count > 1 else ""
    seen = {}

    def rename_tag(match):
        tag = match.group(0)
        id_match = _ID_ATTR_RE.search(tag)
        if not id_match:
            return tag
        original = id_match.group(2)
        seen[original] = seen.get(original, 0) + 1
        repeat = f"-{seen[original]}" if seen[original] > 1 else ""
        if not suffix and not repeat:
            return tag
        renamed = f'{id_match.group(1)}{original}{suffix}{repeat}" data-ak-id="{original}"'
        return tag[: id_match.start()] + renamed + tag[id_match.end() :]

    def rename_refs(match):
        refs = " ".join(ref + suffix if ref in seen else ref for ref in match.group(2).split())
        return f"{match.group(1)}{refs}{match.group(3)}"

    # Markup between <script>/<style> elements, which are kept verbatim.
    raw_elements, markup, last = [], [], 0
    for element in _RAW_TEXT_ELEMENT_RE.finditer(html):
        markup.append(html[last : element.start()])
        raw_elements.append(element.group(0))
        last = element.end()
    markup.append(html[last:])

    markup = [_TAG_RE.sub(rename_tag, piece) for piece in markup]
    if suffix:
        for pattern in _ID_REF_RES:
            markup = [pattern.sub(rename_refs, piece) for piece in markup]
    out = [markup[0]]
    for element, piece in zip(raw_elements, markup[1:]):
        out += [element, piece]
    return "".join(out)


# Shared by every caller that auto-renders a fetched ActionKit form
# (SignupActionKitBlock, the footer newsletter signup) so they hit the same
# cache key format and retry window instead of each keeping its own copy of
# this logic — the same ActionKit page fetched from two call sites should
# still only hit ActionKit's live server at this one shared rate.
EMBED_FORM_SUCCESS_CACHE_TIMEOUT = 60 * 15  # 15 minutes
EMBED_FORM_FAILURE_CACHE_TIMEOUT = 60  # retry a broken/misconfigured page once a minute
# How long the last successfully fetched copy is kept to fall back on. A
# refetch fails now and then (in production, mostly a read timeout from
# act.350.org), and without this every one of those turned into a minute of
# "temporarily unavailable" on whichever worker hit it.
EMBED_FORM_LAST_GOOD_CACHE_TIMEOUT = 60 * 60 * 24 * 7  # 7 days
# Statuses meaning the ActionKit page itself is gone, not that the fetch
# failed: an old copy of its form would only collect signups that ActionKit
# then rejects, so these drop the fallback instead of serving it.
_EMBED_FORM_GONE_STATUSES = {404, 410}
_EMBED_FORM_FETCH_FAILED = "__actionkit_embed_fetch_failed__"


def fetch_and_cache_embed_form_html(hostname, short_form_id):
    """
    Cached wrapper around fetch_embed_form_html().

    Returns the cached (or freshly fetched) form fragment. When a refetch
    fails, it falls back to the last copy fetched successfully (up to
    EMBED_FORM_LAST_GOOD_CACHE_TIMEOUT old), and returns None only when
    there is none, or when ActionKit says the page no longer exists. The
    failure is cached briefly either way, so a broken/misconfigured page
    doesn't get hit on every render, and logged — a silent None here
    previously left no way to tell a timeout apart from a bad short_form_id
    or a genuine ActionKit outage from production logs.
    """
    cache_key = f"wtrx:actionkit_embed:{hostname}:{short_form_id}"
    last_good_key = f"{cache_key}:last_good"
    cached = cache.get(cache_key)
    if cached == _EMBED_FORM_FETCH_FAILED:
        return cache.get(last_good_key)
    if cached is not None:
        return cached

    try:
        html = fetch_embed_form_html(hostname, short_form_id)
    except (ActionKitError, requests.RequestException) as exc:
        page_gone = getattr(exc, "status_code", None) in _EMBED_FORM_GONE_STATUSES
        if page_gone:
            cache.delete(last_good_key)
        fallback = cache.get(last_good_key)
        logger.warning(
            "ActionKit embed form fetch failed for %s/%s: %s%s",
            hostname,
            short_form_id,
            exc,
            " (serving the last good copy)" if fallback else "",
        )
        cache.set(cache_key, _EMBED_FORM_FETCH_FAILED, EMBED_FORM_FAILURE_CACHE_TIMEOUT)
        return fallback

    cache.set(cache_key, html, EMBED_FORM_SUCCESS_CACHE_TIMEOUT)
    cache.set(last_good_key, html, EMBED_FORM_LAST_GOOD_CACHE_TIMEOUT)
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

import logging

import requests
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from wagtail.models import Locale, Page, Site

from .integrations import actionkit
from .integrations.actionkit import ActionKitError
from .site_settings import IntegrationSettings

logger = logging.getLogger(__name__)

ROBOTS_DISALLOWED_PATHS = ("/admin/", "/django-admin/", "/accounts/")

# Hidden bookkeeping fields ActionKit's own fragment adds to the form for its
# own client script and hosted form handler. Not signup data, so not forwarded.
_ACTIONKIT_BOOKKEEPING_FIELDS = {
    "page",
    "utf8",
    "form_name",
    "url",
    "js",
    "auto_country",
    "csrfmiddlewaretoken",
    "want_progress",
}

# ActionKit's spam honeypots: inputs hidden from people (main.css), so only a
# bot fills one in.
_ACTIONKIT_HONEYPOT_FIELDS = ("action_honey", "user_honey")


def _actionkit_embed_fields(post):
    """
    The fields of a submitted ActionKit embed, ready for ActionKit's REST API.

    The form is ActionKit's own fragment, so its inputs already carry the names
    ActionKit expects: core user fields bare, ``user_<name>`` for custom user
    fields, ``action_<name>`` for action fields, plus tracking (``source``,
    ``akid``) and the GDPR opt-in set (``privacy*``, ``required``). They are
    forwarded under those names, so a field ActionKit adds to a page needs no
    change here. Renaming them (as map_form_fields does for a Wagtail form,
    whose names are an editor's labels) turns anything unlisted into a
    ``user_<name>`` field ActionKit rejects the whole signup for.

    Blank values are dropped. An input posted more than once (``required``,
    once per required field) keeps every value, as a list.
    """
    fields = {}
    for key in post:
        if key in _ACTIONKIT_BOOKKEEPING_FIELDS or key in _ACTIONKIT_HONEYPOT_FIELDS:
            continue
        values = [value.strip() for value in post.getlist(key) if value.strip()]
        if values:
            fields[key] = values[0] if len(values) == 1 else values

    # ActionKit's forms ask for one "name"; its REST API takes the two parts.
    name = fields.pop("name", None)
    if isinstance(name, str):
        first_name, _sep, last_name = name.partition(" ")
        fields.setdefault("first_name", first_name)
        if last_name.strip():
            fields.setdefault("last_name", last_name.strip())
    return fields


def robots_txt(request):
    """Tell crawlers where the sitemap is, and to stay out of the admin."""
    lines = [
        "User-agent: *",
        *(f"Disallow: {path}" for path in ROBOTS_DISALLOWED_PATHS),
        "",
        f"Sitemap: {request.build_absolute_uri(reverse('sitemap'))}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


@csrf_exempt
@require_POST
def actionkit_inline_signup(request):
    """
    Same-origin AJAX endpoint for SignupActionKitBlock's inline success_message mode.

    CSRF-exempt on purpose: a token rendered into the form would make every
    page carrying one set a per-visitor cookie, which is what stops the CDN
    caching it (see wtrx/edge_cache.py). The endpoint is anonymous and touches
    nothing tied to the visitor's session, so the token protected very little.

    ActionKit's normal submission is a full-page POST straight to ActionKit's
    own server, which redirects to its thank-you page on success — there's no
    client-side success/failure signal to hook a "show a message instead"
    feature onto. When a block has success_message configured, its template
    posts the form here instead, and we forward it server-side via the
    already-tested integrations.actionkit.submit_action REST call (the same
    one FormPage.process_form_submission uses), which gives an actual
    success/failure result to respond with. This path does not go through
    ActionKit's own recaptcha check — the same trade-off FormPage forwarding
    already accepts.
    """
    short_form_id = request.POST.get("page", "").strip()
    if not short_form_id:
        return JsonResponse(
            {"success": False, "message": _("Missing ActionKit page.")}, status=400
        )

    try:
        integration = IntegrationSettings.for_request(request)
    except (IntegrationSettings.DoesNotExist, Site.DoesNotExist):
        return JsonResponse(
            {"success": False, "message": _("Signup is not configured.")}, status=503
        )

    actionkit_config = integration.get_integration_config("actionkit")
    if not actionkit_config:
        return JsonResponse(
            {"success": False, "message": _("Signup is not configured.")}, status=503
        )

    if any(request.POST.get(name, "").strip() for name in _ACTIONKIT_HONEYPOT_FIELDS):
        # Answer as a real signup would, so a bot learns nothing.
        return JsonResponse({"success": True})

    fields = _actionkit_embed_fields(request.POST)
    if not fields.get("email"):
        return JsonResponse(
            {"success": False, "message": _("Email address is required.")}, status=400
        )

    try:
        action = actionkit.submit_action(
            actionkit_config.get("hostname"),
            actionkit_config.get("api_username"),
            integration.get_actionkit_api_password(),
            short_form_id,
            fields,
        )
    except (ActionKitError, requests.RequestException):
        logger.exception(
            "ActionKit inline signup forwarding failed for page %s.", short_form_id
        )
        return JsonResponse(
            {
                "success": False,
                "message": _("Something went wrong. Please try again."),
            },
            status=502,
        )

    payload = {"success": True}
    redirect = actionkit.signup_redirect(
        actionkit_config.get("hostname"), short_form_id, action
    )
    if redirect:
        (
            payload["redirect_url"],
            payload["redirect_is_actionkit"],
            payload["redirect_is_default"],
        ) = redirect
    return JsonResponse(payload)


def no_cms_access(request):
    """
    Landing page for a logged-in user with no Wagtail admin access.

    Google SSO auto-creates an account for anyone in the allowed domain
    (see allauth_adapter.py), but that alone grants no CMS permissions — a
    superuser still has to add them to an Editor/Moderator group. Before
    that happens, allauth's default post-login redirect
    (NoSignupAccountAdapter.get_login_redirect_url) sends them here instead
    of Django's default `/accounts/profile/`, which isn't a real page in
    this project and 404s.
    """
    return render(request, "wtrx/no_cms_access.html")


def search(request):
    search_query = request.GET.get("query", None)

    if search_query:
        # Scoped to the language being browsed. Each language is its own page
        # tree (one per locale), so an unscoped search returns every site's
        # content at once -- a visitor searching from /brasil/ would get mostly
        # French and Indonesian pages, none of which they can read, and all at
        # URLs outside the site they are on. `get_active()` follows the URL
        # prefix via LocaleMiddleware and falls back to the default locale.
        #
        # Search all live pages in that locale, then post-filter pages that
        # have opted out. hide_from_search sits on each concrete BasePage
        # subclass table, so a single-query ORM filter is not possible without
        # a raw join. The post-filter approach is the accepted Wagtail pattern.
        raw_results = (
            Page.objects.live().filter(locale=Locale.get_active()).search(search_query)
        )
        search_results = [
            p for p in raw_results if not getattr(p.specific, "hide_from_search", False)
        ]
    else:
        search_results = []

    return render(
        request,
        "wtrx/search/search.html",
        {
            "search_query": search_query,
            "search_results": search_results,
        },
    )

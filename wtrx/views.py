import logging

import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from wagtail.models import Page, Site

from .integrations import actionkit
from .integrations.actionkit import ActionKitError
from .site_settings import IntegrationSettings

logger = logging.getLogger(__name__)

# Hidden bookkeeping fields ActionKit's own fragment adds to the form —
# not donor data, so excluded before map_form_fields turns unrecognised
# keys into user_<name> custom fields on the ActionKit record.
_ACTIONKIT_BOOKKEEPING_FIELDS = {
    "page",
    "utf8",
    "form_name",
    "url",
    "js",
    "auto_country",
    "csrfmiddlewaretoken",
}


@require_POST
def actionkit_inline_signup(request):
    """
    Same-origin AJAX endpoint for SignupActionKitBlock's inline success_message mode.

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

    posted = {
        key: value
        for key, value in request.POST.items()
        if key not in _ACTIONKIT_BOOKKEEPING_FIELDS
    }
    fields = actionkit.map_form_fields(posted)
    if not fields.get("email"):
        return JsonResponse(
            {"success": False, "message": _("Email address is required.")}, status=400
        )

    try:
        actionkit.submit_action(
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

    return JsonResponse({"success": True})


def search(request):
    search_query = request.GET.get("query", None)

    if search_query:
        # Search all live pages, then post-filter pages that have opted out.
        # hide_from_search sits on each concrete BasePage subclass table, so a
        # single-query ORM filter is not possible without a raw join. The
        # post-filter approach is the accepted Wagtail pattern.
        raw_results = Page.objects.live().search(search_query)
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

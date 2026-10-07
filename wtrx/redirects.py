"""Redirect middleware that carries the request's query string to the destination."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from wagtail.contrib.redirects import models
from wagtail.contrib.redirects.middleware import RedirectMiddleware, get_redirect

REDIRECT_STATUS_CODES = (301, 302)


def merge_query_string(destination: str, query_string: str) -> str:
    """
    Append ``query_string``'s parameters to ``destination``.

    A parameter the destination already sets is left alone, so a redirect an
    editor pointed at ``/donate/?form=FUNABC`` keeps its own ``form`` whatever
    the visitor arrived with. The destination's fragment is preserved.
    """
    incoming = parse_qsl(query_string, keep_blank_values=True)
    if not incoming:
        return destination

    parts = urlsplit(destination)
    existing = parse_qsl(parts.query, keep_blank_values=True)
    existing_keys = {key for key, _ in existing}
    carried = [(key, value) for key, value in incoming if key not in existing_keys]
    if not carried:
        return destination

    return urlunsplit(parts._replace(query=urlencode(existing + carried)))


class QueryPreservingRedirectMiddleware(RedirectMiddleware):
    """
    Wagtail's ``RedirectMiddleware``, except the visitor's query string survives.

    Stock Wagtail matches ``/about/?gclid=x`` against a redirect stored for
    ``/about`` and then sends the visitor to the bare destination, dropping
    ad click IDs, UTM parameters, ActionKit's ``akid``/``source`` and Fundraise
    Up's ``?form=`` on the way.

    A redirect whose stored "from" path itself includes that query string is a
    deliberate mapping of one specific URL, and is left exactly as Wagtail
    serves it.
    """

    def process_response(self, request, response):
        was_not_found = response.status_code == 404
        response = super().process_response(request, response)

        query_string = request.META.get('QUERY_STRING', '')
        if not was_not_found or not query_string or response.status_code not in REDIRECT_STATUS_CODES:
            return response

        full_path = models.Redirect.normalise_path(request.get_full_path(), decode_unicode=False)
        if get_redirect(request, full_path) is not None:
            return response

        response['Location'] = merge_query_string(response['Location'], query_string)
        return response

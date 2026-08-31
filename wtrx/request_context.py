"""
Lightweight "current request" context, used only so StreamBlock subclasses
(BodyStreamBlock, SectionContentBlock) can tell which site is being edited
when they build the "Add block" picker list — see
IntegrationGatedStreamBlockMixin.sorted_child_blocks() in wtrx/blocks/__init__.py.

Wagtail's StreamBlockAdapter.js_args() (the Telepath adapter that serializes
a StreamBlock's picker definitions for the admin JS) is called with no
request argument, so there is no other way for block code to know which
site's IntegrationSettings should apply.

A contextvars.ContextVar is used rather than threading.local so this stays
correct under async request handling too, not just threaded WSGI.
"""

from contextvars import ContextVar

_current_request = ContextVar("wtrx_current_request", default=None)


def get_current_request():
    return _current_request.get()


class CurrentRequestMiddleware:
    """
    Stashes the current request in a ContextVar for the duration of the
    request/response cycle. Cleared in a finally block so it can never leak
    into a later request handled by the same worker (e.g. if a view raises).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current_request.set(request)
        try:
            return self.get_response(request)
        finally:
            _current_request.reset(token)

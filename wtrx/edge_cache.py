"""Middleware that tells the CDN which responses it may cache."""

from django.conf import settings
from django.utils.cache import patch_cache_control

CACHEABLE_METHODS = ('GET', 'HEAD')


class EdgeCacheMiddleware:
    """
    Add ``Cache-Control: public, max-age=0, s-maxage=N`` to anonymous page views.

    ``s-maxage`` is read by the CDN only; ``max-age=0`` keeps browsers
    revalidating, so a purge on publish (``wtrx/cache.py``) reaches visitors
    straight away. ``N`` is ``WTRX_EDGE_CACHE_SECONDS``; 0 turns this off.

    A response is left alone, and so stays uncached, when anything suggests it
    was built for one visitor:

    - the request carries a session cookie (a logged-in editor, who gets the
      Wagtail userbar, or a visitor who has unlocked a password-protected page);
    - the response sets a cookie -- which is what rendering ``{% csrf_token %}``
      does, so a page with a Django form on it (``FormPage``, the login screen)
      opts itself out;
    - the view already chose its own ``Cache-Control`` (the Wagtail admin).

    The CDN has to be told to honour the header: Cloudflare caches no HTML
    without a Cache Rule. See "Cloudflare page caching" in README.md.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        seconds = settings.WTRX_EDGE_CACHE_SECONDS
        if seconds > 0 and self.is_cacheable(request, response):
            patch_cache_control(response, public=True, max_age=0, s_maxage=seconds)
        return response

    @staticmethod
    def is_cacheable(request, response) -> bool:
        user = getattr(request, 'user', None)
        return (
            request.method in CACHEABLE_METHODS
            and response.status_code == 200
            and not response.streaming
            and not response.cookies
            and not response.has_header('Cache-Control')
            and settings.SESSION_COOKIE_NAME not in request.COOKIES
            and not (user is not None and user.is_authenticated)
            and not getattr(request, 'is_preview', False)
        )

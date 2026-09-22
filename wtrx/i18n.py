"""
Named URL prefixes for language trees: `/france/` rather than `/fr/`.

Django ties a language tree's URL prefix to its language code, so French lives
at `/fr/` and there is no setting to change it. This project's language trees
are the country sites that already exist at `/brasil/`, `/france/`,
`/indonesia/` and `/germany/`, and those URLs are in circulation -- so the
prefix is mapped instead of the pages being moved behind redirects.

`WTRX_LANGUAGE_URL_PREFIXES` (settings) maps a language code to the path
segment it serves under. A language with no entry keeps its own code, and the
default language stays unprefixed as before.

Two pieces have to agree on the mapping, which is why both live here:

- `NamedLocalePrefixPattern` replaces the prefix Django reverses URLs with and
  strips them by. Subclassing matters beyond convenience:
  `is_language_prefix_patterns_used()` identifies i18n URLs with an
  `isinstance` check, and `LocaleMiddleware` reads its answer to decide whether
  to force the default language on an unprefixed path and whether to add
  `Vary: Accept-Language`. A look-alike class would silently lose both.
- `NamedPrefixLocaleMiddleware` resolves the incoming path to a language.
  Django's own `get_language_from_path()` matches the first segment against
  language codes, so `/france/` means nothing to it and it would fall through
  to the Accept-Language header -- serving the French tree in English, or
  404ing it outright.

A language with a mapped prefix is reachable **only** at that prefix: `/fr/`
does not resolve, so each tree has exactly one canonical URL and no competing
duplicate for search engines to index.

`LocalePrefixPattern` is not part of Django's public API. `test_i18n.py`
asserts both directions (resolving and reversing) so a Django upgrade that
changes it fails the suite rather than the site.
"""

from django.conf import settings
from django.middleware.locale import LocaleMiddleware
from django.urls import URLResolver
from django.urls.resolvers import LocalePrefixPattern
from django.utils import translation
from django.utils.translation import get_language


def language_url_prefixes():
    """Map every configured language to the path segment it serves under."""
    overrides = getattr(settings, "WTRX_LANGUAGE_URL_PREFIXES", {})
    return {
        code: overrides.get(code, code)
        for code, _label in getattr(settings, "WAGTAIL_CONTENT_LANGUAGES", [])
    }


def url_prefix_for_language(language_code):
    """The path segment `language_code` serves under, e.g. 'fr' -> 'france'."""
    return language_url_prefixes().get(language_code, language_code)


def language_from_url_prefix(path):
    """
    The language a request path belongs to, or None for the default language.

    Deliberately not Django's `get_language_from_path()`: this matches the
    first path segment against the *mapped* prefixes only, so a language with a
    named prefix is not also reachable at its bare code.
    """
    segment = path.lstrip("/").split("/", 1)[0]
    if not segment:
        return None
    for code, prefix in language_url_prefixes().items():
        if segment == prefix:
            return code
    return None


class NamedLocalePrefixPattern(LocalePrefixPattern):
    """`LocalePrefixPattern` with the prefix read from the mapping."""

    @property
    def language_prefix(self):
        language_code = get_language() or settings.LANGUAGE_CODE
        if language_code == settings.LANGUAGE_CODE and not self.prefix_default_language:
            return ""
        return "%s/" % url_prefix_for_language(language_code)


def named_i18n_patterns(*urls, prefix_default_language=True):
    """
    `django.conf.urls.i18n.i18n_patterns`, with mapped prefixes.

    Same shape as Django's own: one `URLResolver` wrapping the patterns, and a
    plain list when `USE_I18N` is off.
    """
    if not settings.USE_I18N:
        return list(urls)
    return [
        URLResolver(
            NamedLocalePrefixPattern(prefix_default_language=prefix_default_language),
            list(urls),
        )
    ]


class NamedPrefixLocaleMiddleware(LocaleMiddleware):
    """
    `LocaleMiddleware` that recognises a mapped prefix as a language.

    Everything else is deferred to Django: an unprefixed path still gets the
    default language forced onto it (so `/about/` serves English whatever the
    browser asks for), and `Vary: Accept-Language` is still added there and
    only there.
    """

    def process_request(self, request):
        language = language_from_url_prefix(request.path_info)
        if language is None:
            super().process_request(request)
            return
        translation.activate(language)
        request.LANGUAGE_CODE = translation.get_language()

    def process_response(self, request, response):
        if language_from_url_prefix(request.path_info) is None:
            return super().process_response(request, response)
        # A prefixed URL names its own language, so the response does not vary
        # by Accept-Language -- matching Django's handling of `/fr/`-style URLs,
        # and keeping these pages cacheable per-URL at the CDN.
        response.headers.setdefault("Content-Language", translation.get_language())
        return response

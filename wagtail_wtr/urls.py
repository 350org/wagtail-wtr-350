from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from django.views.decorators.cache import cache_control

from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps.views import sitemap

from wtrx.sitemaps import AllLocalesSitemap
from wagtail.documents import urls as wagtaildocs_urls

from wtrx import views
from wtrx.i18n import named_i18n_patterns

SITEMAP_EDGE_CACHE_SECONDS = 60 * 60

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    # Every language tree, not just the default one -- see wtrx/sitemaps.py.
    # Sets its own Cache-Control, so EdgeCacheMiddleware leaves it alone: a
    # sitemap is expensive to build and an hour stale costs nothing, where a
    # page's 10 minutes meant nearly every crawler fetch found it expired.
    path(
        "sitemap.xml",
        cache_control(public=True, max_age=0, s_maxage=SITEMAP_EDGE_CACHE_SECONDS)(sitemap),
        {"sitemaps": {"pages": AllLocalesSitemap}},
        name="sitemap",
    ),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path("i18n/", include("django.conf.urls.i18n")),
    # Health check for zero-downtime deploys (Render, load balancers, etc.)
    path(
        "_health/",
        lambda r: HttpResponse("ok", content_type="text/plain"),
        name="health_check",
    ),
    path(
        "actionkit-signup/",
        views.actionkit_inline_signup,
        name="actionkit_inline_signup",
    ),
]

urlpatterns += named_i18n_patterns(
    path("search/", views.search, name="search"),
    path("no-cms-access/", views.no_cms_access, name="no_cms_access"),
    path("", include(wagtail_urls)),
    # English (the default language) is served at / without a prefix. Every
    # other language is prefixed, by the segment WTRX_LANGUAGE_URL_PREFIXES
    # maps it to (/brasil/, /france/) or by its own code where it maps to
    # nothing (/es/). See wtrx/i18n.py for why both the pattern and the
    # middleware are ours.
    prefix_default_language=False,
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

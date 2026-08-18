from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps.views import sitemap
from wagtail.documents import urls as wagtaildocs_urls

from wtrx import views

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("sitemap.xml", sitemap, name="sitemap"),
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

urlpatterns += i18n_patterns(
    path("search/", views.search, name="search"),
    path("no-cms-access/", views.no_cms_access, name="no_cms_access"),
    path("", include(wagtail_urls)),
    # English (the default language) is served at / without a language prefix.
    # Non-default languages added by forks are still prefixed (e.g. /es/).
    # LocaleMiddleware handles language detection; see base.py LANGUAGES setting.
    prefix_default_language=False,
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

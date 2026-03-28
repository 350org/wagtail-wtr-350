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

from wtrx import views as search_views

urlpatterns = [
    path("django-admin/", admin.site.urls),
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
]

urlpatterns += i18n_patterns(
    path("search/", search_views.search, name="search"),
    path("", include(wagtail_urls)),
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

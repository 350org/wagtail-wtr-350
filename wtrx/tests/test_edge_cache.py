from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.http import HttpResponse, StreamingHttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from wagtail.models import Page, Site

from wtrx.edge_cache import EdgeCacheMiddleware
from wtrx.models import HomePage

AK_FORM_TEMPLATE = (
    Path(settings.BASE_DIR) / "wtrx/templates/wtrx/components/streamfield/blocks/_actionkit_form.html"
)


@override_settings(WTRX_EDGE_CACHE_SECONDS=600)
class EdgeCacheMiddlewareTests(SimpleTestCase):
    def _run(self, request=None, response=None, user=None):
        request = request or RequestFactory().get("/about/")
        request.user = user or AnonymousUser()
        response = response or HttpResponse("ok")
        return EdgeCacheMiddleware(lambda _request: response)(request)

    def test_anonymous_page_view_is_cacheable_at_the_edge_only(self):
        self.assertEqual(self._run()["Cache-Control"], "public, max-age=0, s-maxage=600")

    def test_request_without_a_user_attribute_is_treated_as_anonymous(self):
        request = RequestFactory().get("/about/")
        response = EdgeCacheMiddleware(lambda _request: HttpResponse("ok"))(request)
        self.assertIn("s-maxage=600", response["Cache-Control"])

    @override_settings(WTRX_EDGE_CACHE_SECONDS=0)
    def test_zero_seconds_turns_it_off(self):
        self.assertFalse(self._run().has_header("Cache-Control"))

    def test_post_is_not_cacheable(self):
        response = self._run(request=RequestFactory().post("/about/"))
        self.assertFalse(response.has_header("Cache-Control"))

    def test_non_200_is_not_cacheable(self):
        for status in (301, 404, 500):
            with self.subTest(status=status):
                response = self._run(response=HttpResponse("x", status=status))
                self.assertFalse(response.has_header("Cache-Control"))

    def test_streaming_response_is_not_cacheable(self):
        response = self._run(response=StreamingHttpResponse(iter(["x"])))
        self.assertFalse(response.has_header("Cache-Control"))

    def test_response_setting_a_cookie_is_not_cacheable(self):
        response = HttpResponse("form")
        response.set_cookie("csrftoken", "abc")
        self.assertFalse(self._run(response=response).has_header("Cache-Control"))

    def test_request_with_a_session_cookie_is_not_cacheable(self):
        request = RequestFactory().get("/about/")
        request.COOKIES[settings.SESSION_COOKIE_NAME] = "abc"
        self.assertFalse(self._run(request=request).has_header("Cache-Control"))

    def test_logged_in_user_is_not_cacheable(self):
        response = self._run(user=User(username="editor"))
        self.assertFalse(response.has_header("Cache-Control"))

    def test_preview_is_not_cacheable(self):
        request = RequestFactory().get("/about/")
        request.is_preview = True
        self.assertFalse(self._run(request=request).has_header("Cache-Control"))

    def test_a_view_that_set_its_own_cache_control_keeps_it(self):
        response = HttpResponse("admin")
        response["Cache-Control"] = "no-store"
        self.assertEqual(self._run(response=response)["Cache-Control"], "no-store")


@override_settings(WTRX_EDGE_CACHE_SECONDS=600)
class EdgeCacheThroughTheStackTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Site.objects.filter(is_default_site=True).delete()
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-edge-cache")
        root.add_child(instance=cls.home)
        Site.objects.create(hostname="localhost", port=80, root_page=cls.home, is_default_site=True)

    def test_anonymous_page_sets_no_cookie_and_is_cacheable(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.cookies)
        self.assertIn("s-maxage=600", response["Cache-Control"])

    def test_logged_in_editor_gets_an_uncached_page(self):
        self.client.force_login(User.objects.create_superuser("editor", "e@example.com", "pw"))
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("s-maxage", response.get("Cache-Control", ""))

    def test_admin_login_page_is_not_cacheable(self):
        response = self.client.get(reverse("wagtailadmin_login"))
        self.assertNotIn("s-maxage", response.get("Cache-Control", ""))


class ActionKitSignupNeedsNoCsrfTokenTests(TestCase):
    def test_form_template_renders_no_csrf_token(self):
        # A token here sets a per-visitor cookie on every page with a signup
        # form, which stops the CDN caching any of them.
        self.assertNotIn("csrf_token", AK_FORM_TEMPLATE.read_text())

    def test_endpoint_accepts_a_post_without_a_token(self):
        response = Client(enforce_csrf_checks=True).post(reverse("actionkit_inline_signup"), {})
        self.assertEqual(response.status_code, 400)  # "Missing ActionKit page", not a 403

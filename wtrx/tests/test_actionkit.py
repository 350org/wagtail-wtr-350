"""
Tests for the ActionKit signup integration.

Covers:
- map_form_fields: standard label mapping, single-name split, custom-field
  passthrough, and the no-email case.
- submit_action: URL construction, HTTP Basic auth, JSON body, success on 2xx,
  and ActionKitError on non-2xx.
- FormPage.process_form_submission: forwards to ActionKit when the platform is
  "actionkit" and a page is set; a forwarding failure is swallowed/logged and
  the local submission is still saved.
- fetch_embed_form_html: URL/query-param construction, success, and error cases.
- SignupActionKitBlock.get_context: fetches and caches the embed fragment,
  caches (and rate-limits retrying) failures, and degrades gracefully when
  unconfigured.
"""

from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from wagtail.models import Page, Site

from wtrx.blocks import SignupActionKitBlock
from wtrx.integrations import actionkit
from wtrx.integrations.actionkit import ActionKitError
from wtrx.models import FormField, FormPage, HomePage
from wtrx.site_settings import IntegrationSettings


class TestMapFormFields(SimpleTestCase):
    def test_maps_standard_fields(self):
        result = actionkit.map_form_fields(
            {
                "email": "a@b.com",
                "first_name": "Alice",
                "last_name": "Smith",
                "zip_code": "94110",
                "phone_number": "555-1234",
            }
        )
        self.assertEqual(result["email"], "a@b.com")
        self.assertEqual(result["first_name"], "Alice")
        self.assertEqual(result["last_name"], "Smith")
        self.assertEqual(result["zip"], "94110")
        self.assertEqual(result["phone"], "555-1234")

    def test_single_name_field_splits_into_first_and_last(self):
        result = actionkit.map_form_fields({"email": "a@b.com", "name": "Alice Q Smith"})
        self.assertEqual(result["first_name"], "Alice")
        self.assertEqual(result["last_name"], "Q Smith")

    def test_explicit_first_last_take_precedence_over_name_split(self):
        result = actionkit.map_form_fields(
            {
                "email": "a@b.com",
                "first_name": "Given",
                "name": "Ignored Name",
            }
        )
        self.assertEqual(result["first_name"], "Given")

    def test_unrecognised_field_becomes_custom_user_field(self):
        result = actionkit.map_form_fields(
            {"email": "a@b.com", "favorite_color": "blue"}
        )
        self.assertEqual(result["user_favorite_color"], "blue")

    def test_blank_values_are_dropped(self):
        result = actionkit.map_form_fields(
            {"email": "a@b.com", "phone": "", "note": None}
        )
        self.assertNotIn("phone", result)
        self.assertNotIn("user_note", result)

    def test_missing_email_yields_no_email_key(self):
        result = actionkit.map_form_fields({"name": "Alice"})
        self.assertNotIn("email", result)

    def test_actionkit_native_utm_fields_pass_through_unprefixed(self):
        result = actionkit.map_form_fields(
            {
                "email": "a@b.com",
                "action_utm_source": "newsletter",
                "action_utm_medium": "email",
                "action_utm_campaign": "spring-drive",
                "action_utm_term": "climate",
                "action_utm_content": "header-link",
            }
        )
        self.assertEqual(result["action_utm_source"], "newsletter")
        self.assertEqual(result["action_utm_medium"], "email")
        self.assertEqual(result["action_utm_campaign"], "spring-drive")
        self.assertEqual(result["action_utm_term"], "climate")
        self.assertEqual(result["action_utm_content"], "header-link")
        # Must not also land under a user_ prefix.
        self.assertNotIn("user_action_utm_source", result)

    def test_blank_utm_fields_are_dropped_not_forwarded_empty(self):
        result = actionkit.map_form_fields({"email": "a@b.com", "action_utm_source": ""})
        self.assertNotIn("action_utm_source", result)


class TestSubmitAction(SimpleTestCase):
    def _mock_response(self, status_code=201, text=""):
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = text
        return resp

    @patch("wtrx.integrations.actionkit.requests.post")
    def test_posts_to_rest_action_endpoint_with_auth_and_body(self, mock_post):
        mock_post.return_value = self._mock_response(201)
        actionkit.submit_action(
            "myorg.actionkit.com",
            "apiuser",
            "secret",
            "join",
            {"email": "a@b.com", "first_name": "Alice"},
        )
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://myorg.actionkit.com/rest/v1/action/")
        self.assertEqual(kwargs["auth"], ("apiuser", "secret"))
        self.assertEqual(kwargs["json"]["page"], "join")
        self.assertEqual(kwargs["json"]["email"], "a@b.com")
        self.assertEqual(kwargs["json"]["first_name"], "Alice")

    @patch("wtrx.integrations.actionkit.requests.post")
    def test_accepts_full_url_hostname(self, mock_post):
        mock_post.return_value = self._mock_response(200)
        actionkit.submit_action(
            "https://myorg.actionkit.com/",
            "u",
            "p",
            "join",
            {"email": "a@b.com"},
        )
        self.assertEqual(
            mock_post.call_args[0][0], "https://myorg.actionkit.com/rest/v1/action/"
        )

    @patch("wtrx.integrations.actionkit.requests.post")
    def test_non_2xx_raises_actionkit_error(self, mock_post):
        mock_post.return_value = self._mock_response(422, text="bad page")
        with self.assertRaises(ActionKitError):
            actionkit.submit_action(
                "myorg.actionkit.com", "u", "p", "join", {"email": "a@b.com"}
            )

    def test_missing_config_raises_actionkit_error(self):
        with self.assertRaises(ActionKitError):
            actionkit.submit_action("", "u", "p", "join", {"email": "a@b.com"})


class TestFormPageActionKitForwarding(TestCase):
    @classmethod
    def setUpTestData(cls):
        Site.objects.filter(is_default_site=True).delete()
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-ak")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="localhost",
            port=80,
            root_page=cls.home,
            is_default_site=True,
        )
        cls.form_page = FormPage(
            title="Join",
            slug="join-ak",
            to_address="test@example.com",
            from_address="noreply@example.com",
            subject="New signup",
            actionkit_page="join",
        )
        cls.home.add_child(instance=cls.form_page)
        FormField.objects.create(
            page=cls.form_page,
            sort_order=0,
            label="Email",
            field_type="email",
            required=True,
        )
        FormField.objects.create(
            page=cls.form_page,
            sort_order=1,
            label="Your name",
            field_type="singleline",
            required=True,
        )

    def _configure_platform(self, platform):
        IntegrationSettings.objects.update_or_create(
            site=self.site,
            defaults={
                "signup_platform": platform,
                "actionkit_hostname": "myorg.actionkit.com",
                "actionkit_api_username": "apiuser",
                "actionkit_api_password": "secret",
            },
        )

    def _submit(self):
        return self.client.post(
            self.form_page.url,
            {"email": "a@b.com", "your_name": "Alice Smith"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    @patch("wtrx.integrations.actionkit.submit_action")
    def test_forwards_when_platform_is_actionkit(self, mock_submit):
        self._configure_platform("actionkit")
        response = self._submit()
        self.assertEqual(response.status_code, 200)
        mock_submit.assert_called_once()
        args, _ = mock_submit.call_args
        # (hostname, username, password, page, fields)
        self.assertEqual(args[3], "join")
        self.assertEqual(args[4]["email"], "a@b.com")
        self.assertEqual(args[4]["first_name"], "Alice")

    @patch("wtrx.integrations.actionkit.submit_action")
    def test_does_not_forward_when_platform_is_wagtail_forms(self, mock_submit):
        self._configure_platform("wagtail_forms")
        response = self._submit()
        self.assertEqual(response.status_code, 200)
        mock_submit.assert_not_called()

    @patch("wtrx.integrations.actionkit.submit_action")
    def test_forwarding_failure_is_swallowed_and_submission_saved(self, mock_submit):
        mock_submit.side_effect = requests.RequestException("boom")
        self._configure_platform("actionkit")
        response = self._submit()
        # User still sees success despite the ActionKit failure.
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        # The local submission was still stored.
        self.assertEqual(self.form_page.get_submission_class().objects.count(), 1)


class TestFetchEmbedFormHTML(SimpleTestCase):
    def _mock_response(self, status_code=200, text="<form>...</form>"):
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = text
        return resp

    @patch("wtrx.integrations.actionkit.requests.get")
    def test_requests_form_only_fragment_with_abs_urls(self, mock_get):
        mock_get.return_value = self._mock_response()
        html = actionkit.fetch_embed_form_html("myorg.actionkit.com", "join")
        self.assertEqual(html, "<form>...</form>")
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], "https://myorg.actionkit.com/act/join")
        self.assertEqual(kwargs["params"], {"form_only": 1, "abs_urls": 1})

    @patch("wtrx.integrations.actionkit.requests.get")
    def test_accepts_full_url_hostname(self, mock_get):
        mock_get.return_value = self._mock_response()
        actionkit.fetch_embed_form_html("https://myorg.actionkit.com/", "join")
        self.assertEqual(
            mock_get.call_args[0][0], "https://myorg.actionkit.com/act/join"
        )

    @patch("wtrx.integrations.actionkit.requests.get")
    def test_non_2xx_raises_actionkit_error(self, mock_get):
        mock_get.return_value = self._mock_response(404, text="not found")
        with self.assertRaises(ActionKitError):
            actionkit.fetch_embed_form_html("myorg.actionkit.com", "nope")

    def test_missing_config_raises_actionkit_error(self):
        with self.assertRaises(ActionKitError):
            actionkit.fetch_embed_form_html("", "join")
        with self.assertRaises(ActionKitError):
            actionkit.fetch_embed_form_html("myorg.actionkit.com", "")


class TestSignupActionKitBlockContext(TestCase):
    """SignupActionKitBlock.get_context() fetches, caches, and degrades gracefully."""

    @classmethod
    def setUpTestData(cls):
        Site.objects.filter(is_default_site=True).delete()
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-ak-embed")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="localhost",
            port=80,
            root_page=cls.home,
            is_default_site=True,
        )
        IntegrationSettings.objects.update_or_create(
            site=cls.site,
            defaults={
                "signup_platform": "actionkit",
                "actionkit_hostname": "myorg.actionkit.com",
            },
        )

    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    def _value(self, short_form_id="join"):
        block = SignupActionKitBlock()
        return block.to_python(
            {
                "heading": "Sign up",
                "description": "",
                "short_form_id": short_form_id,
                "anchor_id": "",
            }
        )

    @patch("wtrx.blocks.actionkit.fetch_embed_form_html")
    def test_fetches_and_caches_on_success(self, mock_fetch):
        mock_fetch.return_value = "<form>hello</form>"
        block = SignupActionKitBlock()
        request = self.factory.get("/")
        ctx = block.get_context(self._value(), parent_context={"request": request})

        self.assertEqual(ctx["form_html"], "<form>hello</form>")
        self.assertEqual(ctx["actionkit_base_url"], "https://myorg.actionkit.com")
        mock_fetch.assert_called_once_with("myorg.actionkit.com", "join")

        # Second render within the cache window does not hit ActionKit again.
        block.get_context(self._value(), parent_context={"request": request})
        mock_fetch.assert_called_once()

    @patch("wtrx.blocks.actionkit.fetch_embed_form_html")
    def test_fetch_failure_degrades_to_none_and_is_cached(self, mock_fetch):
        mock_fetch.side_effect = ActionKitError("boom")
        block = SignupActionKitBlock()
        request = self.factory.get("/")

        ctx = block.get_context(self._value(), parent_context={"request": request})
        self.assertIsNone(ctx["form_html"])

        # A second attempt within the failure-cache window doesn't retry.
        ctx2 = block.get_context(self._value(), parent_context={"request": request})
        self.assertIsNone(ctx2["form_html"])
        mock_fetch.assert_called_once()

    def test_no_request_in_context_yields_no_form_html(self):
        block = SignupActionKitBlock()
        ctx = block.get_context(self._value(), parent_context=None)
        self.assertIsNone(ctx["form_html"])

    def test_blank_short_form_id_yields_no_form_html(self):
        block = SignupActionKitBlock()
        request = self.factory.get("/")
        ctx = block.get_context(
            self._value(short_form_id=""), parent_context={"request": request}
        )
        self.assertIsNone(ctx["form_html"])


class TestActionKitInlineSignupView(TestCase):
    """
    views.actionkit_inline_signup — the endpoint SignupActionKitBlock's
    success_message mode posts to instead of letting ActionKit's own
    onsubmit chain do a full-page POST straight to ActionKit.
    """

    @classmethod
    def setUpTestData(cls):
        Site.objects.filter(is_default_site=True).delete()
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-ak-inline")
        root.add_child(instance=cls.home)
        cls.site = Site.objects.create(
            hostname="localhost",
            port=80,
            root_page=cls.home,
            is_default_site=True,
        )

    def _configure_platform(self, platform="actionkit"):
        IntegrationSettings.objects.update_or_create(
            site=self.site,
            defaults={
                "signup_platform": platform,
                "actionkit_hostname": "myorg.actionkit.com",
                "actionkit_api_username": "apiuser",
                "actionkit_api_password": "secret",
            },
        )

    def _post(self, data):
        return self.client.post(reverse("actionkit_inline_signup"), data)

    @patch("wtrx.views.actionkit.submit_action")
    def test_forwards_via_submit_action_and_strips_bookkeeping_fields(
        self, mock_submit
    ):
        self._configure_platform()
        response = self._post(
            {
                "page": "web_join",
                "email": "a@b.com",
                "name": "Alice Smith",
                # ActionKit's own hidden bookkeeping fields — must not leak
                # into ActionKit as bogus user_<name> custom fields.
                "utf8": "✔",
                "form_name": "act",
                "url": "http://localhost:8000/",
                "js": "1",
                "auto_country": "1",
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        mock_submit.assert_called_once()
        args, _ = mock_submit.call_args
        # (hostname, username, password, page, fields)
        self.assertEqual(args[3], "web_join")
        fields = args[4]
        self.assertEqual(fields["email"], "a@b.com")
        self.assertEqual(fields["first_name"], "Alice")
        for bookkeeping_field in ("page", "utf8", "form_name", "url", "js", "auto_country"):
            self.assertNotIn(f"user_{bookkeeping_field}", fields)

    def test_missing_page_returns_400_without_calling_submit_action(self):
        self._configure_platform()
        with patch("wtrx.views.actionkit.submit_action") as mock_submit:
            response = self._post({"email": "a@b.com"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        mock_submit.assert_not_called()

    def test_missing_email_returns_400_without_calling_submit_action(self):
        self._configure_platform()
        with patch("wtrx.views.actionkit.submit_action") as mock_submit:
            response = self._post({"page": "web_join", "name": "Alice"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        mock_submit.assert_not_called()

    def test_wrong_platform_returns_503_without_calling_submit_action(self):
        self._configure_platform(platform="wagtail_forms")
        with patch("wtrx.views.actionkit.submit_action") as mock_submit:
            response = self._post({"page": "web_join", "email": "a@b.com"})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["success"])
        mock_submit.assert_not_called()

    @patch("wtrx.views.actionkit.submit_action")
    def test_submit_action_error_returns_502(self, mock_submit):
        mock_submit.side_effect = ActionKitError("boom")
        self._configure_platform()
        response = self._post({"page": "web_join", "email": "a@b.com"})
        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.json()["success"])

    def test_get_request_not_allowed(self):
        self._configure_platform()
        response = self.client.get(reverse("actionkit_inline_signup"))
        self.assertEqual(response.status_code, 405)

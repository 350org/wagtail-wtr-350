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
"""

from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, TestCase
from wagtail.models import Page, Site

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

"""
Tests for the ActionKit signup integration.

Covers:
- map_form_fields: standard label mapping, single-name split, custom-field
  passthrough, and the no-email case.
- submit_action: URL construction, HTTP Basic auth, JSON body (including the
  default "source": "website"), success on 2xx, and ActionKitError on non-2xx.
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
    def test_defaults_source_to_website(self, mock_post):
        # Without an explicit "source", ActionKit's REST endpoint stamps its
        # own "restful_api" default -- our submissions are really website
        # visitors using our own embedded forms, not API integration traffic.
        mock_post.return_value = self._mock_response(201)
        actionkit.submit_action(
            "myorg.actionkit.com", "apiuser", "secret", "join", {"email": "a@b.com"}
        )
        self.assertEqual(mock_post.call_args.kwargs["json"]["source"], "website")

    @patch("wtrx.integrations.actionkit.requests.post")
    def test_an_explicit_source_field_wins_over_the_default(self, mock_post):
        mock_post.return_value = self._mock_response(201)
        actionkit.submit_action(
            "myorg.actionkit.com",
            "apiuser",
            "secret",
            "join",
            {"email": "a@b.com", "source": "newsletter"},
        )
        self.assertEqual(mock_post.call_args.kwargs["json"]["source"], "newsletter")

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

    @patch("wtrx.integrations.actionkit.requests.post")
    def test_returns_the_response_body(self, mock_post):
        resp = self._mock_response(201)
        resp.json.return_value = {"id": 7, "redirect_url": "/cms/thanks/join?action_id=7"}
        mock_post.return_value = resp
        result = actionkit.submit_action(
            "myorg.actionkit.com", "u", "p", "join", {"email": "a@b.com"}
        )
        self.assertEqual(result["redirect_url"], "/cms/thanks/join?action_id=7")

    @patch("wtrx.integrations.actionkit.requests.post")
    def test_returns_empty_dict_when_body_is_not_json(self, mock_post):
        resp = self._mock_response(201)
        resp.json.side_effect = ValueError
        mock_post.return_value = resp
        result = actionkit.submit_action(
            "myorg.actionkit.com", "u", "p", "join", {"email": "a@b.com"}
        )
        self.assertEqual(result, {})


class TestSignupRedirect(SimpleTestCase):
    """signup_redirect: which ActionKit after-action redirects get followed."""

    HOST = "myorg.actionkit.com"

    def _redirect(self, redirect_url, page="join"):
        return actionkit.signup_redirect(self.HOST, page, {"redirect_url": redirect_url})

    def test_default_thanks_page_is_flagged_as_default(self):
        # Every ActionKit page has this when nobody set a redirect, so it is
        # only followed when the block has no thank-you handling of its own.
        self.assertEqual(
            self._redirect("/cms/thanks/join?action_id=7&akid=.1.abc"),
            ("https://myorg.actionkit.com/cms/thanks/join?action_id=7&akid=.1.abc", True, True),
        )
        self.assertEqual(
            self._redirect("https://myorg.actionkit.com/cms/thanks/join/?action_id=7"),
            ("https://myorg.actionkit.com/cms/thanks/join/?action_id=7", True, True),
        )

    def test_another_actionkit_page_keeps_action_id_and_is_flagged(self):
        url, is_actionkit, is_default = self._redirect("/donate/give?action_id=7&akid=.1.abc")
        self.assertEqual(
            url, "https://myorg.actionkit.com/donate/give?action_id=7&akid=.1.abc"
        )
        self.assertTrue(is_actionkit)
        self.assertFalse(is_default)

    def test_another_pages_thanks_page_is_not_the_default(self):
        url, is_actionkit, is_default = self._redirect("/cms/thanks/other?action_id=7")
        self.assertEqual(url, "https://myorg.actionkit.com/cms/thanks/other?action_id=7")
        self.assertTrue(is_actionkit)
        self.assertFalse(is_default)

    def test_external_page_is_not_flagged_as_actionkit(self):
        url, is_actionkit, is_default = self._redirect("https://example.org/welcome/?action_id=7")
        self.assertEqual(url, "https://example.org/welcome/?action_id=7")
        self.assertFalse(is_actionkit)
        self.assertFalse(is_default)

    def test_non_http_and_missing_redirects_are_ignored(self):
        self.assertIsNone(self._redirect("javascript:alert(1)"))
        self.assertIsNone(self._redirect(""))
        self.assertIsNone(actionkit.signup_redirect(self.HOST, "join", {}))
        self.assertIsNone(actionkit.signup_redirect(self.HOST, "join", None))


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

    def _configure_actionkit(self, enabled=True):
        IntegrationSettings.objects.update_or_create(
            site=self.site,
            defaults={
                "integrations": [
                    (
                        "actionkit",
                        {
                            "enabled": enabled,
                            "hostname": "myorg.actionkit.com",
                            "api_username": "apiuser",
                            "api_password": "secret",
                        },
                    )
                ],
            },
        )

    def _submit(self):
        return self.client.post(
            self.form_page.url,
            {"email": "a@b.com", "your_name": "Alice Smith"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    @patch("wtrx.integrations.actionkit.submit_action")
    def test_forwards_when_actionkit_enabled(self, mock_submit):
        self._configure_actionkit()
        response = self._submit()
        self.assertEqual(response.status_code, 200)
        mock_submit.assert_called_once()
        args, _ = mock_submit.call_args
        # (hostname, username, password, page, fields)
        self.assertEqual(args[3], "join")
        self.assertEqual(args[4]["email"], "a@b.com")
        self.assertEqual(args[4]["first_name"], "Alice")

    @patch("wtrx.integrations.actionkit.submit_action")
    def test_does_not_forward_when_actionkit_not_enabled(self, mock_submit):
        self._configure_actionkit(enabled=False)
        response = self._submit()
        self.assertEqual(response.status_code, 200)
        mock_submit.assert_not_called()

    @patch("wtrx.integrations.actionkit.submit_action")
    def test_forwarding_failure_is_swallowed_and_submission_saved(self, mock_submit):
        mock_submit.side_effect = requests.RequestException("boom")
        self._configure_actionkit()
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

    @patch("wtrx.integrations.actionkit.requests.get")
    def test_recaptcha_script_is_made_async(self, mock_get):
        mock_get.return_value = self._mock_response(
            text='<form>...</form><script src="https://www.google.com/recaptcha/api.js"></script>'
        )
        html = actionkit.fetch_embed_form_html("myorg.actionkit.com", "join")
        self.assertIn(
            '<script src="https://www.google.com/recaptcha/api.js" async>', html
        )

    @patch("wtrx.integrations.actionkit.requests.get")
    def test_country_label_for_attribute_is_fixed(self, mock_get):
        mock_get.return_value = self._mock_response(
            text=(
                '<label for="id_email">Email Address</label>'
                '<input type="text" name="email" id="id_email">'
                '<label for="id_country">Country</label>'
                '<select name="country" id="country"></select>'
            )
        )
        html = actionkit.fetch_embed_form_html("myorg.actionkit.com", "join")
        self.assertIn('<label for="country">Country</label>', html)
        # The (already-correct) email label/input pairing must be untouched.
        self.assertIn('<label for="id_email">Email Address</label>', html)


# Trimmed from a real act.350.org petition fragment (/act/ppg): the header
# sits beside the form inside #action-lead, and on a petition carries both
# a description wrapper and the no-JS petition-text box.
PETITION_FRAGMENT = """
<section id="action-lead" class="section action-lead">
<div class="section-inner">
    <div id="action-header" class="c6">
        <a id="jump-to-form" href="#action-form">Add Your Name</a>
        <p id="action-pretitle"><span class="highlight">Tell PM Carney:</span></p>
        <h2 id="action-title" class="title3"><span>Build a People's Power Grid</span></h2>
        <div id="action-description" class="text-large">
            <div id="action-description-text" data-read-more-after="6">
                <meta charset="utf-8" />
                <p>We demand a grid.</p>
                <p><a href="https://example.org"><img src="https://cdn.example/logo.png" width="150"></a></p>
            </div>
            <p class="no-js-hidden petition-text-link">
                <a href="https://act.350.org" class="js-modal" data-modal-source="#petition-text">
                    View the full petition text.
                </a>
            </p>
            <div class="js-hidden box">
                <div id="petition-text">
                    <p>Full text.</p>
                    <div><iframe src="https://www.youtube.com/embed/x" width="560"></iframe></div>
                </div>
            </div>
        </div>
    </div>
    <form id="action-form" name="act"><script>jQuery(function(){ if (1 < 2) {} });</script>
        <input type="text" name="email"></form>
    <div id="recent-actions"></div>
</div>
</section>
"""


class TestStripSubmitArrow(SimpleTestCase):
    """A typed-in trailing arrow is removed; the CSS icon is the only arrow."""

    def test_strips_trailing_arrow_from_submit_button(self):
        html = '<button type="submit" class="submit button-primary">Junte-se a nós →</button>'
        self.assertEqual(
            actionkit._strip_submit_arrow(html),
            '<button type="submit" class="submit button-primary">Junte-se a nós</button>',
        )

    def test_strips_arrow_entity(self):
        html = '<button class="x" type="submit">Rejoignez-nous &rarr; </button>'
        self.assertEqual(actionkit._strip_submit_arrow(html), '<button class="x" type="submit">Rejoignez-nous</button>')

    def test_strips_arrow_from_submit_input_value(self):
        self.assertEqual(
            actionkit._strip_submit_arrow('<input type="submit" value="Join →">'),
            '<input type="submit" value="Join">',
        )

    def test_leaves_labels_without_an_arrow_alone(self):
        html = '<button type="submit">Join Us</button>'
        self.assertEqual(actionkit._strip_submit_arrow(html), html)

    def test_leaves_non_submit_buttons_alone(self):
        html = '<button type="button">Next →</button>'
        self.assertEqual(actionkit._strip_submit_arrow(html), html)


class TestSplitActionHeader(SimpleTestCase):
    def test_extracts_intro_parts(self):
        intro, _html = actionkit.split_action_header(PETITION_FRAGMENT)
        self.assertEqual(intro["pretitle"], "Tell PM Carney:")
        self.assertEqual(intro["title"], "Build a People's Power Grid")
        self.assertIn("<p>We demand a grid.</p>", intro["description_html"])
        self.assertIn('src="https://cdn.example/logo.png"', intro["description_html"])
        self.assertIn("<p>Full text.</p>", intro["petition_html"])
        self.assertEqual(intro["petition_link_text"], "View the full petition text.")

    def test_description_excludes_petition_chrome_and_meta(self):
        intro, _html = actionkit.split_action_header(PETITION_FRAGMENT)
        self.assertNotIn("js-modal", intro["description_html"])
        self.assertNotIn("Full text.", intro["description_html"])
        self.assertNotIn("<meta", intro["description_html"])

    def test_header_removed_and_form_left_byte_for_byte(self):
        _intro, html = actionkit.split_action_header(PETITION_FRAGMENT)
        self.assertNotIn('id="action-header"', html)
        self.assertNotIn("jump-to-form", html)
        form_start = PETITION_FRAGMENT.index("<form")
        self.assertEqual(html[html.index("<form"):], PETITION_FRAGMENT[form_start:])
        self.assertTrue(html.startswith(PETITION_FRAGMENT[: PETITION_FRAGMENT.index('<div id="action-header"')]))

    def test_embedded_iframes_get_a_referrer_policy(self):
        # Without one, the site's same-origin Referrer-Policy makes YouTube
        # refuse to play the embed.
        intro, _html = actionkit.split_action_header(PETITION_FRAGMENT)
        self.assertIn('referrerpolicy="strict-origin-when-cross-origin"', intro["petition_html"])

    def test_letter_without_petition_text(self):
        fragment = (
            '<section id="action-lead"><div id="action-header">'
            '<h2 id="action-title">No Pipelines</h2>'
            '<div id="action-description"><p>Copy.</p></div>'
            '</div><form id="action-form"></form></section>'
        )
        intro, html = actionkit.split_action_header(fragment)
        self.assertEqual(intro["title"], "No Pipelines")
        self.assertEqual(intro["description_html"], "<p>Copy.</p>")
        self.assertEqual(intro["petition_html"], "")
        self.assertEqual(intro["petition_link_text"], "")
        self.assertEqual(html, '<section id="action-lead"><form id="action-form"></form></section>')

    def test_fragment_without_header_is_returned_unchanged(self):
        for fragment in ("<form id=\"action-form\"></form>", "", None):
            intro, html = actionkit.split_action_header(fragment)
            self.assertIsNone(intro)
            self.assertEqual(html, fragment)


class TestUniquifyFormIds(SimpleTestCase):
    """A page with several ActionKit embeds must not repeat the fragment's ids."""

    FRAGMENT = (
        '<section id="action-lead"><form id="action-form" name="act">'
        '<div id="ak-fieldbox-email"><label for="id_email">Email</label>'
        '<input type="text" name="email" id="id_email" aria-describedby="ak-errors other"></div>'
        '<a href="#action-form">Jump</a><a href="#elsewhere">Away</a>'
        "<script>document.getElementById(\"id_email\"); var s = '<p id=\"x\">';</script>"
        '<ul id="ak-errors"><li></li></ul></form></section>'
    )

    def setUp(self):
        self.request = RequestFactory().get("/")

    def test_first_embed_is_unchanged(self):
        self.assertEqual(actionkit.uniquify_form_ids(self.FRAGMENT, self.request), self.FRAGMENT)

    def test_later_embeds_get_suffixed_ids_and_references(self):
        actionkit.uniquify_form_ids(self.FRAGMENT, self.request)
        html = actionkit.uniquify_form_ids(self.FRAGMENT, self.request)
        self.assertIn('<form id="action-form--2" data-ak-id="action-form" name="act">', html)
        self.assertIn('<label for="id_email--2">', html)
        self.assertIn('id="id_email--2" data-ak-id="id_email"', html)
        self.assertIn('aria-describedby="ak-errors--2 other"', html)
        self.assertIn('href="#action-form--2"', html)
        # A fragment link to an id the fragment doesn't own is left alone.
        self.assertIn('href="#elsewhere"', html)
        self.assertNotIn(' id="ak-errors"', html)

        third = actionkit.uniquify_form_ids(self.FRAGMENT, self.request)
        self.assertIn('id="action-form--3"', third)

    def test_scripts_are_left_byte_for_byte(self):
        actionkit.uniquify_form_ids(self.FRAGMENT, self.request)
        html = actionkit.uniquify_form_ids(self.FRAGMENT, self.request)
        self.assertIn("<script>document.getElementById(\"id_email\"); var s = '<p id=\"x\">';</script>", html)

    def test_repeats_within_one_embed_are_renamed(self):
        fragment = '<p>Hi <span id="known_user_name"></span></p><p>Not <span id="known_user_name"></span>?</p>'
        first = actionkit.uniquify_form_ids(fragment, self.request)
        self.assertEqual(
            first,
            '<p>Hi <span id="known_user_name"></span></p>'
            '<p>Not <span id="known_user_name-2" data-ak-id="known_user_name"></span>?</p>',
        )
        second = actionkit.uniquify_form_ids(fragment, self.request)
        self.assertIn('id="known_user_name--2" data-ak-id', second)
        self.assertIn('id="known_user_name--2-2" data-ak-id', second)

    def test_counts_per_request(self):
        actionkit.uniquify_form_ids(self.FRAGMENT, self.request)
        other_request = RequestFactory().get("/")
        self.assertEqual(actionkit.uniquify_form_ids(self.FRAGMENT, other_request), self.FRAGMENT)

    def test_no_request_or_html_is_a_no_op(self):
        self.assertEqual(actionkit.uniquify_form_ids(self.FRAGMENT, None), self.FRAGMENT)
        self.assertIsNone(actionkit.uniquify_form_ids(None, self.request))
        self.assertEqual(getattr(self.request, "_wtrx_actionkit_form_count", 0), 0)


class TestSignupActionKitIntroRendering(SimpleTestCase):
    """The copy column falls back to ActionKit's own intro only when Content is blank."""

    INTRO = {
        "pretitle": "Tell PM Carney:",
        "title": "Build a Grid",
        "description_html": '<p>AK copy.</p><p><img src="https://cdn.example/logo.png"></p>',
        "petition_html": "<p>Full petition.</p>",
        "petition_link_text": "View the full petition text.",
    }

    def _render(self, context=None, **fields):
        from django.template.loader import render_to_string

        value = SignupActionKitBlock().to_python({"short_form_id": "ppg", **fields})
        return render_to_string(
            "wtrx/components/streamfield/blocks/_actionkit_intro.html",
            {"value": value, "ak_intro": self.INTRO, "bg": "dark-grey", "on_light": False, **(context or {})},
        )

    def test_preview_marks_an_empty_copy_column(self):
        empty = {"ak_intro": None}
        for flag in ("is_page_preview", "is_block_preview"):
            self.assertIn("wtr-actionkit-preview-notice", self._render({**empty, flag: True}))
        # Never on the live site, and never once there is copy to show.
        self.assertNotIn("wtr-actionkit-preview-notice", self._render(empty))
        self.assertNotIn("wtr-actionkit-preview-notice", self._render({"is_page_preview": True}))
        self.assertNotIn(
            "wtr-actionkit-preview-notice",
            self._render({**empty, "is_page_preview": True}, content="<h2>Editor heading</h2>"),
        )

    def test_blank_content_uses_actionkit_copy(self):
        html = self._render()
        self.assertIn("Tell PM Carney:", html)
        self.assertIn("<h2>Build a Grid</h2>", html)
        self.assertIn("<p>AK copy.</p>", html)
        self.assertIn('src="https://cdn.example/logo.png"', html)

    def test_editor_content_wins_and_suppresses_actionkit_pretitle(self):
        html = self._render(content="<h2>Editor heading</h2>")
        self.assertIn("Editor heading", html)
        self.assertNotIn("Build a Grid", html)
        self.assertNotIn("AK copy.", html)
        self.assertNotIn("wtr-signup-eyebrow", html)

    def test_editor_eyebrow_wins_over_pretitle(self):
        html = self._render(eyebrow="Sign now")
        self.assertIn("Sign now", html)
        self.assertNotIn("Tell PM Carney:", html)

    def test_petition_modal_renders_whether_or_not_content_is_set(self):
        for fields in ({}, {"content": "<p>Editor copy.</p>"}):
            html = self._render(**fields)
            self.assertIn("data-ak-petition-trigger", html)
            self.assertIn("View the full petition text.", html)
            self.assertIn("<p>Full petition.</p>", html)


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
                "integrations": [
                    (
                        "actionkit",
                        {
                            "enabled": True,
                            "hostname": "myorg.actionkit.com",
                            "api_username": "",
                            "api_password": "",
                        },
                    )
                ],
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
    def test_missing_form_shows_a_placeholder_in_page_preview_only(self, mock_fetch):
        mock_fetch.side_effect = ActionKitError("boom")
        block = SignupActionKitBlock()
        for is_preview in (True, False):
            request = self.factory.get("/")
            request.is_preview = is_preview
            html = block.render(self._value(), context={"request": request})
            self.assertEqual("wtr-actionkit-preview-notice" in html, is_preview)
            self.assertEqual("temporarily unavailable" in html, not is_preview)

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

    def _expire_fresh_copy(self):
        cache.delete("wtrx:actionkit_embed:myorg.actionkit.com:join")

    @patch("wtrx.blocks.actionkit.fetch_embed_form_html")
    def test_failed_refetch_serves_the_last_good_copy(self, mock_fetch):
        block = SignupActionKitBlock()
        mock_fetch.return_value = "<form>hello</form>"
        block.get_context(self._value(), parent_context={"request": self.factory.get("/")})

        self._expire_fresh_copy()
        mock_fetch.side_effect = requests.ReadTimeout("Read timed out.")
        with self.assertLogs("wtrx.integrations.actionkit", "WARNING") as logs:
            ctx = block.get_context(self._value(), parent_context={"request": self.factory.get("/")})
        self.assertEqual(ctx["form_html"], "<form>hello</form>")
        self.assertIn("serving the last good copy", logs.output[0])

        # Within the failure window it keeps serving that copy without retrying.
        ctx = block.get_context(self._value(), parent_context={"request": self.factory.get("/")})
        self.assertEqual(ctx["form_html"], "<form>hello</form>")
        self.assertEqual(mock_fetch.call_count, 2)

    @patch("wtrx.blocks.actionkit.fetch_embed_form_html")
    def test_a_deleted_actionkit_page_drops_the_last_good_copy(self, mock_fetch):
        block = SignupActionKitBlock()
        mock_fetch.return_value = "<form>hello</form>"
        block.get_context(self._value(), parent_context={"request": self.factory.get("/")})

        self._expire_fresh_copy()
        mock_fetch.side_effect = ActionKitError("ActionKit returned HTTP 404", status_code=404)
        with self.assertLogs("wtrx.integrations.actionkit", "WARNING"):
            ctx = block.get_context(self._value(), parent_context={"request": self.factory.get("/")})
        self.assertIsNone(ctx["form_html"])

    @patch("wtrx.blocks.actionkit.fetch_embed_form_html")
    def test_lifts_actionkit_intro_out_of_form_html(self, mock_fetch):
        mock_fetch.return_value = PETITION_FRAGMENT
        block = SignupActionKitBlock()
        request = self.factory.get("/")
        ctx = block.get_context(self._value(), parent_context={"request": request})
        self.assertEqual(ctx["ak_intro"]["title"], "Build a People's Power Grid")
        self.assertNotIn('id="action-header"', ctx["form_html"])
        self.assertIn('id="action-form"', ctx["form_html"])

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

    def _configure_actionkit(self, enabled=True):
        IntegrationSettings.objects.update_or_create(
            site=self.site,
            defaults={
                "integrations": [
                    (
                        "actionkit",
                        {
                            "enabled": enabled,
                            "hostname": "myorg.actionkit.com",
                            "api_username": "apiuser",
                            "api_password": "secret",
                        },
                    )
                ],
            },
        )

    def _post(self, data):
        return self.client.post(reverse("actionkit_inline_signup"), data)

    @patch("wtrx.views.actionkit.submit_action")
    def test_forwards_via_submit_action_and_strips_bookkeeping_fields(
        self, mock_submit
    ):
        self._configure_actionkit()
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

    @patch("wtrx.views.actionkit.submit_action")
    def test_default_thanks_redirect_is_returned_flagged_as_default(self, mock_submit):
        mock_submit.return_value = {"redirect_url": "/cms/thanks/web_join?action_id=7"}
        self._configure_actionkit()
        response = self._post({"page": "web_join", "email": "a@b.com"})
        self.assertEqual(
            response.json(),
            {
                "success": True,
                "redirect_url": "https://myorg.actionkit.com/cms/thanks/web_join?action_id=7",
                "redirect_is_actionkit": True,
                "redirect_is_default": True,
            },
        )

    @patch("wtrx.views.actionkit.submit_action")
    def test_custom_redirect_is_returned(self, mock_submit):
        mock_submit.return_value = {"redirect_url": "https://example.org/welcome/?action_id=7"}
        self._configure_actionkit()
        response = self._post({"page": "web_join", "email": "a@b.com"})
        self.assertEqual(
            response.json(),
            {
                "success": True,
                "redirect_url": "https://example.org/welcome/?action_id=7",
                "redirect_is_actionkit": False,
                "redirect_is_default": False,
            },
        )

    @patch("wtrx.views.actionkit.submit_action")
    def test_actionkit_hosted_redirect_is_flagged(self, mock_submit):
        mock_submit.return_value = {"redirect_url": "/donate/give?action_id=7"}
        self._configure_actionkit()
        response = self._post({"page": "web_join", "email": "a@b.com"})
        self.assertEqual(
            response.json()["redirect_url"],
            "https://myorg.actionkit.com/donate/give?action_id=7",
        )
        self.assertTrue(response.json()["redirect_is_actionkit"])

    def test_missing_page_returns_400_without_calling_submit_action(self):
        self._configure_actionkit()
        with patch("wtrx.views.actionkit.submit_action") as mock_submit:
            response = self._post({"email": "a@b.com"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        mock_submit.assert_not_called()

    def test_missing_email_returns_400_without_calling_submit_action(self):
        self._configure_actionkit()
        with patch("wtrx.views.actionkit.submit_action") as mock_submit:
            response = self._post({"page": "web_join", "name": "Alice"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        mock_submit.assert_not_called()

    def test_actionkit_not_enabled_returns_503_without_calling_submit_action(self):
        self._configure_actionkit(enabled=False)
        with patch("wtrx.views.actionkit.submit_action") as mock_submit:
            response = self._post({"page": "web_join", "email": "a@b.com"})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["success"])
        mock_submit.assert_not_called()

    @patch("wtrx.views.actionkit.submit_action")
    def test_submit_action_error_returns_502(self, mock_submit):
        mock_submit.side_effect = ActionKitError("boom")
        self._configure_actionkit()
        response = self._post({"page": "web_join", "email": "a@b.com"})
        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.json()["success"])

    def test_get_request_not_allowed(self):
        self._configure_actionkit()
        response = self.client.get(reverse("actionkit_inline_signup"))
        self.assertEqual(response.status_code, 405)

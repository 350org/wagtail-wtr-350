"""
Tests for FormField and FormPage models.

WagtailPageTests covers parent/subpage type constraints.
TestCase with RequestFactory covers get_context() behaviour.
"""

from django.test import RequestFactory, TestCase
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTests

from wtrx.models import (
    ContentPage,
    FormField,
    FormPage,
    HomePage,
    IndexPage,
)


class TestFormPageParentSubpageTypes(WagtailPageTests):
    """FormPage parent/subpage type constraints."""

    def test_can_create_under_home_page(self):
        self.assertCanCreateAt(HomePage, FormPage)

    def test_can_create_under_content_page(self):
        self.assertCanCreateAt(ContentPage, FormPage)

    def test_can_create_under_index_page(self):
        self.assertCanCreateAt(IndexPage, FormPage)

    def test_cannot_create_under_form_page(self):
        self.assertCanNotCreateAt(FormPage, FormPage)

    def test_can_not_create_under_root(self):
        self.assertCanNotCreateAt(Page, FormPage)

    def test_no_allowed_subpage_types(self):
        self.assertAllowedSubpageTypes(FormPage, [])


class TestFormPageGetContext(TestCase):
    """FormPage.get_context() must populate a minimal hero dict."""

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-fp")
        root.add_child(instance=cls.home)
        cls.form_page = FormPage(
            title="Sign Up",
            slug="sign-up",
            to_address="test@example.com",
            from_address="noreply@example.com",
            subject="New submission",
        )
        cls.home.add_child(instance=cls.form_page)

    def _get_context(self, page):
        request = RequestFactory().get("/")
        return page.get_context(request)

    def test_hero_dict_present(self):
        ctx = self._get_context(self.form_page)
        self.assertIn("hero", ctx)

    def test_hero_headline_uses_page_title(self):
        ctx = self._get_context(self.form_page)
        self.assertEqual(ctx["hero"]["headline"], "Sign Up")

    def test_hero_copy_is_none(self):
        ctx = self._get_context(self.form_page)
        self.assertIsNone(ctx["hero"]["copy"])

    def test_hero_image_is_none(self):
        ctx = self._get_context(self.form_page)
        self.assertIsNone(ctx["hero"]["image"])

    def test_hero_video_is_none(self):
        ctx = self._get_context(self.form_page)
        self.assertIsNone(ctx["hero"]["video"])

    def test_hero_link_page_is_none(self):
        ctx = self._get_context(self.form_page)
        self.assertIsNone(ctx["hero"]["link_page"])

    def test_hero_link_url_is_none(self):
        ctx = self._get_context(self.form_page)
        self.assertIsNone(ctx["hero"]["link_url"])

    def test_hero_copy_is_block_is_false(self):
        ctx = self._get_context(self.form_page)
        self.assertFalse(ctx["hero"]["copy_is_block"])

    def test_hero_dict_has_all_required_keys(self):
        ctx = self._get_context(self.form_page)
        expected = {
            "headline",
            "copy",
            "copy_is_block",
            "image",
            "video",
            "link_text",
            "link_page",
            "link_url",
        }
        self.assertEqual(set(ctx["hero"].keys()), expected)


class TestFormFieldParentalKey(TestCase):
    """FormField.page ParentalKey points to FormPage with correct related_name."""

    def test_related_name_is_form_fields(self):
        field = FormField._meta.get_field("page")
        self.assertEqual(field.related_query_name(), "form_fields")

    def test_parental_key_to_form_page(self):
        from modelcluster.fields import ParentalKey

        field = FormField._meta.get_field("page")
        self.assertIsInstance(field, ParentalKey)
        self.assertEqual(field.related_model, FormPage)


class TestFormPageMeta(TestCase):
    def test_verbose_name(self):
        self.assertEqual(FormPage._meta.verbose_name, "form page")

    def test_verbose_name_plural(self):
        self.assertEqual(FormPage._meta.verbose_name_plural, "form pages")


class TestFormPageContentPanels(TestCase):
    """FormPage.content_panels must include email notification fields."""

    def test_content_panels_include_to_address(self):
        panel_fields = [getattr(p, "field_name", None) for p in FormPage.content_panels]
        # to_address is nested in a MultiFieldPanel — walk all panels
        all_fields = []

        def collect_fields(panels):
            for p in panels:
                fn = getattr(p, "field_name", None)
                if fn:
                    all_fields.append(fn)
                children = getattr(p, "children", None)
                if children:
                    collect_fields(children)

        collect_fields(FormPage.content_panels)
        self.assertIn("to_address", all_fields)
        self.assertIn("from_address", all_fields)
        self.assertIn("subject", all_fields)
        self.assertIn("intro", all_fields)
        self.assertIn("thank_you_text", all_fields)


class TestFormPageServeAjax(TestCase):
    """FormPage.serve() must return JSON for AJAX requests."""

    @classmethod
    def setUpTestData(cls):
        # Remove any pre-existing default site so we control the tree.
        Site.objects.filter(is_default_site=True).delete()
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-ajax")
        root.add_child(instance=cls.home)
        # Create a default site rooted at home so page.url works correctly.
        Site.objects.create(
            hostname="localhost",
            port=80,
            root_page=cls.home,
            is_default_site=True,
        )
        cls.form_page = FormPage(
            title="Contact",
            slug="contact-ajax",
            to_address="test@example.com",
            from_address="noreply@example.com",
            subject="New submission",
        )
        cls.home.add_child(instance=cls.form_page)
        # Add a required text field so the form has something to validate.
        FormField.objects.create(
            page=cls.form_page,
            sort_order=0,
            label="Your name",
            field_type="singleline",
            required=True,
        )

    def test_ajax_invalid_post_returns_json_400(self):
        """POSTing an incomplete AJAX form returns 400 with errors JSON."""
        response = self.client.post(
            self.form_page.url,
            {},  # missing required "your_name" field
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("errors", data)

    def test_ajax_valid_post_returns_json_success(self):
        """POSTing a complete AJAX form returns 200 with success JSON."""
        response = self.client.post(
            self.form_page.url,
            {"your_name": "Alice"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

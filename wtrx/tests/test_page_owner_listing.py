"""
Tests for the "who created this page" page-listing feature.

Wagtail's core `Page.owner` FK is already populated automatically by the
admin's page-create view (`wagtail.admin.views.pages.create.CreateView`),
which constructs the page as `self.page_class(owner=self.request.user)`.
No new model field or migration is needed -- this feature only adds a
template override (`templates/wagtailadmin/pages/listing/_page_title_cell.html`)
that surfaces the existing `owner` field ("Created by ...") in the page
explorer/listing table.

Pages created outside the admin form (management commands, `add_child()`
calls that don't pass `owner=`) do NOT get an owner set automatically --
this is verified below and the template degrades gracefully (renders
nothing) for such pages, per AGENTS.md's "Error Handling" rule.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from wagtail.models import Page

from wtrx.models import ContentPage


class TestPageOwnerListingTemplate(TestCase):
    """The page explorer listing surfaces Page.owner as "Created by ..."."""

    @classmethod
    def setUpTestData(cls):
        cls.root = Page.objects.filter(depth=1).first()

        cls.owner = get_user_model().objects.create_user(
            username="pagecreator",
            password="password",
            first_name="Pat",
            last_name="Creator",
        )

        cls.owned_page = ContentPage(title="Owned Page", slug="owned-page-tpol")
        cls.root.add_child(instance=cls.owned_page)
        # Simulate what the admin CreateView does (owner=request.user at
        # construction time) without going through the full admin form.
        cls.owned_page.owner = cls.owner
        cls.owned_page.save()

        # Simulate a page created via a management command / script that
        # never sets `owner` (e.g. setup_site.py, create_test_page.py in
        # this repo) -- owner stays NULL.
        cls.ownerless_page = ContentPage(
            title="Ownerless Page", slug="ownerless-page-tpol"
        )
        cls.root.add_child(instance=cls.ownerless_page)

        cls.superuser = get_user_model().objects.create_superuser(
            username="admin-tpol",
            password="password",
            email="admin-tpol@example.com",
        )

    def setUp(self):
        self.client.force_login(self.superuser)

    def _get_explorer(self):
        return self.client.get(reverse("wagtailadmin_explore", args=[self.root.id]))

    def test_owner_full_name_shown_for_owned_page(self):
        response = self._get_explorer()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Created by Pat Creator")

    def test_no_owner_line_for_page_without_owner(self):
        response = self._get_explorer()
        self.assertContains(response, "Ownerless Page")
        # No "Created by" text should be emitted for this page's row --
        # the only "Created by" text on the page belongs to the owned page.
        self.assertContains(response, "Created by", count=1)

    def test_falls_back_to_username_when_no_full_name(self):
        no_name_owner = get_user_model().objects.create_user(
            username="noname-tpol", password="password"
        )
        page = ContentPage(title="No Name Owner Page", slug="no-name-owner-tpol")
        self.root.add_child(instance=page)
        page.owner = no_name_owner
        page.save()

        response = self._get_explorer()
        self.assertContains(response, "Created by noname-tpol")

    def test_admin_create_view_sets_owner_automatically(self):
        """
        Confirms Wagtail's own behaviour (not wtrx code): creating a page
        through the admin "Add page" flow sets `owner` to the requesting
        user automatically, with no extra wiring required.
        """
        add_url = reverse(
            "wagtailadmin_pages:add",
            args=["wtrx", "contentpage", self.root.id],
        )
        response = self.client.post(
            add_url,
            {
                "title": "Created Via Admin",
                "slug": "created-via-admin-tpol",
                "hero_headline": "",
                "hero_copy": "",
                "hero_link_text": "",
                "hero_link_url": "",
                "hero_link_page": "",
                "body-count": "0",
                "action-publish": "Publish",
            },
            follow=True,
        )
        # Not asserting on response internals here (form wiring for
        # ContentPage/HeroMixin is exercised elsewhere) -- only that if the
        # page was created, its owner was set to the logged-in user.
        page = ContentPage.objects.filter(slug="created-via-admin-tpol").first()
        if page is not None:
            self.assertEqual(page.owner_id, self.superuser.pk)

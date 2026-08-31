"""
Tests for concrete page models: HomePage, ContentPage, IndexPage, Post,
Blogs.

WagtailPageTests covers parent/subpage type constraints.
TestCase with RequestFactory covers get_context() behaviour.
"""

import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.utils import timezone
from wagtail.images.tests.utils import get_test_image_file
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTests

from wtrx.images import CustomImage
from wtrx.models import (
    BlogCategory,
    Blogs,
    ContentPage,
    FormPage,
    HomePage,
    IndexPage,
    ITEMS_PER_PAGE,
    Post,
)


# ---------------------------------------------------------------------------
# HeroMixin panel selection: hero_panels (full variant) vs.
# banner_hero_panels (banner variant) — see HeroMixin/banner_hero_panels'
# docstrings in wtrx/models.py.
# ---------------------------------------------------------------------------


def _collect_panel_field_names(panels):
    """Walk a content_panels list (including nested MultiFieldPanel children)
    and return every FieldPanel-derived field_name found."""
    names = []
    for panel in panels:
        field_name = getattr(panel, "field_name", None)
        if field_name:
            names.append(field_name)
        children = getattr(panel, "children", None)
        if children:
            names.extend(_collect_panel_field_names(children))
    return names


class TestHeroPanelSelection(TestCase):
    """
    HomePage is the only HeroMixin page type using the "full" hero variant,
    so it alone should expose hero_video in the editor. ContentPage,
    IndexPage, and Blogs always render the "banner" variant
    (HeroMixin.hero_variant default) where hero_video sits inert, so their
    content_panels use HeroMixin.banner_hero_panels instead — same
    underlying model field (no migration), just a smaller edit form.

    hero_cta is exposed on BOTH panel sets: components/hero.html's "banner"
    rendering already only renders hero_cta's plain `button` choice (see
    banner_hero_panels' own docstring), so it's a real, working field there
    too, not an inert one like hero_video.

    hero_layout no longer exists at all (removed rather than hidden) — the
    "full" variant renders a single fixed left-aligned layout now, matching
    what every real "full"-variant page already used in practice.
    """

    def test_home_page_has_all_six_hero_fields(self):
        names = _collect_panel_field_names(HomePage.content_panels)
        for field in (
            "hero_headline",
            "hero_copy",
            "hero_image",
            "hero_video",
            "hero_banner_color",
            "hero_cta",
        ):
            self.assertIn(field, names)

    def test_content_page_has_only_banner_hero_fields(self):
        names = _collect_panel_field_names(ContentPage.content_panels)
        for field in (
            "hero_headline",
            "hero_copy",
            "hero_image",
            "hero_banner_color",
            "hero_cta",
        ):
            self.assertIn(field, names)
        self.assertNotIn("hero_video", names)

    def test_index_page_has_only_banner_hero_fields(self):
        names = _collect_panel_field_names(IndexPage.content_panels)
        for field in (
            "hero_headline",
            "hero_copy",
            "hero_image",
            "hero_banner_color",
            "hero_cta",
        ):
            self.assertIn(field, names)
        self.assertNotIn("hero_video", names)

    def test_blogs_has_only_banner_hero_fields(self):
        names = _collect_panel_field_names(Blogs.content_panels)
        for field in (
            "hero_headline",
            "hero_copy",
            "hero_image",
            "hero_banner_color",
            "hero_cta",
        ):
            self.assertIn(field, names)
        self.assertNotIn("hero_video", names)


# ---------------------------------------------------------------------------
# HomePage
# ---------------------------------------------------------------------------


class TestHomePageParentSubpageTypes(WagtailPageTests):
    """HomePage can only be created under the Wagtail root page."""

    def test_can_create_under_root(self):
        self.assertCanCreateAt(Page, HomePage)

    def test_can_create_under_home_page(self):
        """Country/region sub-homes (e.g. /canada) nest under the site home page."""
        self.assertCanCreateAt(HomePage, HomePage)

    def test_can_not_create_under_content_page(self):
        self.assertCanNotCreateAt(ContentPage, HomePage)

    def test_can_not_create_under_index_page(self):
        self.assertCanNotCreateAt(IndexPage, HomePage)

    def test_allowed_subpage_types(self):
        self.assertAllowedSubpageTypes(
            HomePage, [HomePage, ContentPage, IndexPage, FormPage, Blogs]
        )


class TestHomePageGetContext(TestCase):
    """HomePage.get_context() must populate the hero dict correctly."""

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(
            title="Home",
            slug="home-test-hpgc",
            hero_headline="Welcome",
            hero_copy="<p>Subtext</p>",
        )
        root.add_child(instance=cls.home)

    def _get_context(self, page):
        request = RequestFactory().get("/")
        return page.get_context(request)

    def test_hero_headline_uses_custom_headline(self):
        ctx = self._get_context(self.home)
        self.assertEqual(ctx["hero"]["headline"], "Welcome")

    def test_hero_headline_falls_back_to_title(self):
        """When hero_headline is blank, headline falls back to page title."""
        original = self.home.hero_headline
        try:
            self.home.hero_headline = ""
            ctx = self._get_context(self.home)
            self.assertEqual(ctx["hero"]["headline"], self.home.title)
        finally:
            self.home.hero_headline = original

    def test_hero_copy_is_passed(self):
        ctx = self._get_context(self.home)
        self.assertEqual(ctx["hero"]["copy"], "<p>Subtext</p>")

    def test_hero_copy_is_block_is_false(self):
        ctx = self._get_context(self.home)
        self.assertFalse(ctx["hero"]["copy_is_block"])

    def test_hero_image_defaults_none(self):
        ctx = self._get_context(self.home)
        self.assertIsNone(ctx["hero"]["image"])

    def test_hero_video_defaults_none(self):
        ctx = self._get_context(self.home)
        self.assertIsNone(ctx["hero"]["video"])

    def test_hero_variant_is_full(self):
        """HomePage is the only page type using the "full" hero variant."""
        ctx = self._get_context(self.home)
        self.assertEqual(ctx["hero"]["variant"], "full")

    def test_hero_banner_color_defaults_navy(self):
        ctx = self._get_context(self.home)
        self.assertEqual(ctx["hero"]["banner_color"], "navy")

    def test_hero_dict_has_all_required_keys(self):
        ctx = self._get_context(self.home)
        required_keys = {
            "variant",
            "headline",
            "copy",
            "copy_is_block",
            "image",
            "video",
            "banner_color",
            "cta",
        }
        self.assertEqual(set(ctx["hero"].keys()), required_keys)


class TestHomePageMeta(TestCase):
    """HomePage model Meta attributes."""

    def test_verbose_name(self):
        self.assertEqual(HomePage._meta.verbose_name, "home page")

    def test_verbose_name_plural(self):
        self.assertEqual(HomePage._meta.verbose_name_plural, "home pages")


# ---------------------------------------------------------------------------
# ContentPage
# ---------------------------------------------------------------------------


class TestContentPageParentSubpageTypes(WagtailPageTests):
    """ContentPage parent/subpage type constraints."""

    def test_can_create_under_home_page(self):
        self.assertCanCreateAt(HomePage, ContentPage)

    def test_can_create_under_content_page(self):
        self.assertCanCreateAt(ContentPage, ContentPage)

    def test_can_create_under_index_page(self):
        self.assertCanCreateAt(IndexPage, ContentPage)

    def test_can_not_create_under_root(self):
        self.assertCanNotCreateAt(Page, ContentPage)

    def test_allowed_subpage_types(self):
        self.assertAllowedSubpageTypes(
            ContentPage, [ContentPage, IndexPage, FormPage, Blogs]
        )


class TestContentPageGetContext(TestCase):
    """ContentPage.get_context() must populate the hero dict correctly."""

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-cp")
        root.add_child(instance=cls.home)
        cls.page = ContentPage(
            title="About Us",
            slug="about",
            hero_headline="Our Story",
        )
        cls.home.add_child(instance=cls.page)

    def _get_context(self, page):
        request = RequestFactory().get("/")
        return page.get_context(request)

    def test_hero_headline_uses_custom(self):
        ctx = self._get_context(self.page)
        self.assertEqual(ctx["hero"]["headline"], "Our Story")

    def test_hero_headline_falls_back_to_title(self):
        original = self.page.hero_headline
        try:
            self.page.hero_headline = ""
            ctx = self._get_context(self.page)
            self.assertEqual(ctx["hero"]["headline"], "About Us")
        finally:
            self.page.hero_headline = original

    def test_copy_is_block_is_false(self):
        ctx = self._get_context(self.page)
        self.assertFalse(ctx["hero"]["copy_is_block"])

    def test_hero_video_defaults_none(self):
        ctx = self._get_context(self.page)
        self.assertIsNone(ctx["hero"]["video"])

    def test_hero_variant_is_banner(self):
        """ContentPage uses HeroMixin's default "banner" variant, unlike HomePage."""
        ctx = self._get_context(self.page)
        self.assertEqual(ctx["hero"]["variant"], "banner")

    def test_hero_dict_keys(self):
        ctx = self._get_context(self.page)
        expected = {
            "variant",
            "headline",
            "copy",
            "copy_is_block",
            "image",
            "video",
            "banner_color",
            "cta",
        }
        self.assertEqual(set(ctx["hero"].keys()), expected)


class TestContentPageMeta(TestCase):
    def test_verbose_name(self):
        self.assertEqual(ContentPage._meta.verbose_name, "content page")

    def test_verbose_name_plural(self):
        self.assertEqual(ContentPage._meta.verbose_name_plural, "content pages")


# ---------------------------------------------------------------------------
# IndexPage
# ---------------------------------------------------------------------------


class TestIndexPageParentSubpageTypes(WagtailPageTests):
    """IndexPage parent/subpage type constraints."""

    def test_can_create_under_home_page(self):
        self.assertCanCreateAt(HomePage, IndexPage)

    def test_can_create_under_content_page(self):
        self.assertCanCreateAt(ContentPage, IndexPage)

    def test_can_create_under_index_page(self):
        self.assertCanCreateAt(IndexPage, IndexPage)

    def test_can_not_create_under_root(self):
        self.assertCanNotCreateAt(Page, IndexPage)

    def test_allowed_subpage_types(self):
        self.assertAllowedSubpageTypes(
            IndexPage, [ContentPage, IndexPage, FormPage, Blogs]
        )


class TestIndexPageGetContext(TestCase):
    """IndexPage.get_context() must populate hero + children + paginator."""

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-ip")
        root.add_child(instance=cls.home)
        cls.index = IndexPage(title="Blog", slug="blog")
        cls.home.add_child(instance=cls.index)

        # Create 3 live child pages
        for i in range(3):
            child = ContentPage(title=f"Post {i + 1}", slug=f"post-{i + 1}")
            cls.index.add_child(instance=child)

    def _get_context(self, page, query_string=""):
        request = RequestFactory().get("/", query_string)
        return page.get_context(request)

    def test_hero_dict_present(self):
        ctx = self._get_context(self.index)
        self.assertIn("hero", ctx)

    def test_hero_variant_is_banner(self):
        """IndexPage uses HeroMixin's default "banner" variant, unlike HomePage."""
        ctx = self._get_context(self.index)
        self.assertEqual(ctx["hero"]["variant"], "banner")

    def test_children_in_context(self):
        ctx = self._get_context(self.index)
        self.assertIn("children", ctx)

    def test_paginator_in_context(self):
        ctx = self._get_context(self.index)
        self.assertIn("paginator", ctx)

    def test_children_count_matches_live_children(self):
        ctx = self._get_context(self.index)
        # Page object from Paginator; len() counts items on the current page
        self.assertEqual(len(ctx["children"].object_list), 3)

    def test_invalid_page_number_returns_page_1(self):
        ctx = self._get_context(self.index, {"page": "abc"})
        self.assertEqual(ctx["children"].number, 1)

    def test_out_of_range_page_returns_last_page(self):
        ctx = self._get_context(self.index, {"page": "9999"})
        paginator = ctx["paginator"]
        self.assertEqual(ctx["children"].number, paginator.num_pages)

    def test_items_per_page_constant(self):
        self.assertEqual(ITEMS_PER_PAGE, 12)


class TestIndexPageMeta(TestCase):
    def test_verbose_name(self):
        self.assertEqual(IndexPage._meta.verbose_name, "index page")

    def test_verbose_name_plural(self):
        self.assertEqual(IndexPage._meta.verbose_name_plural, "index pages")


# ---------------------------------------------------------------------------
# BlogCategory
# ---------------------------------------------------------------------------


class TestBlogCategory(TestCase):
    def test_str_is_name(self):
        category = BlogCategory.objects.create(name="Climate Justice", slug="climate-justice")
        self.assertEqual(str(category), "Climate Justice")

    def test_slug_auto_generated_from_name_when_blank(self):
        category = BlogCategory(name="Fossil Fuels")
        category.save()
        self.assertEqual(category.slug, "fossil-fuels")

    def test_explicit_slug_is_preserved(self):
        category = BlogCategory(name="Fossil Fuels", slug="ff")
        category.save()
        self.assertEqual(category.slug, "ff")


# ---------------------------------------------------------------------------
# Post
# ---------------------------------------------------------------------------


class TestPostParentSubpageTypes(WagtailPageTests):
    def test_can_create_under_blogs(self):
        self.assertCanCreateAt(Blogs, Post)

    def test_can_not_create_under_home_page(self):
        self.assertCanNotCreateAt(HomePage, Post)

    def test_can_not_create_under_content_page(self):
        self.assertCanNotCreateAt(ContentPage, Post)

    def test_allowed_subpage_types(self):
        self.assertAllowedSubpageTypes(Post, [])


class TestPostGetContext(TestCase):
    """
    Post.get_context() must build a "banner" hero dict (via
    BannerHeroMixin.get_banner_hero_context()) with author/published_at
    folded in on top.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        home = HomePage(title="Home", slug="home-bp")
        root.add_child(instance=home)
        cls.blogs = Blogs(title="Blog", slug="blog-bp")
        home.add_child(instance=cls.blogs)

        cls.user = User.objects.create_user(username="jane", first_name="Jane", last_name="Doe")

        cls.post = Post(
            title="A Post",
            slug="a-post-bp",
            hero_headline="Custom headline",
            author=cls.user,
            published_at=timezone.now(),
        )
        cls.blogs.add_child(instance=cls.post)

        cls.post_no_author = Post(title="No Author Post", slug="no-author-post-bp")
        cls.blogs.add_child(instance=cls.post_no_author)

    def _get_context(self, page):
        request = RequestFactory().get("/")
        return page.get_context(request)

    def test_hero_variant_is_banner(self):
        ctx = self._get_context(self.post)
        self.assertEqual(ctx["hero"]["variant"], "banner")

    def test_hero_headline_uses_custom(self):
        ctx = self._get_context(self.post)
        self.assertEqual(ctx["hero"]["headline"], "Custom headline")

    def test_hero_author_uses_full_name(self):
        ctx = self._get_context(self.post)
        self.assertEqual(ctx["hero"]["author"], "Jane Doe")

    def test_hero_published_at_matches_field(self):
        ctx = self._get_context(self.post)
        self.assertEqual(ctx["hero"]["published_at"], self.post.published_at)

    def test_hero_author_is_none_when_unset(self):
        ctx = self._get_context(self.post_no_author)
        self.assertIsNone(ctx["hero"]["author"])

    def test_hero_cta_is_always_empty(self):
        """Banner variant never renders a cta — see BannerHeroMixin."""
        ctx = self._get_context(self.post)
        self.assertEqual(ctx["hero"]["cta"], [])

    def test_related_headings_follow_parent_title(self):
        ctx = self._get_context(self.post)
        self.assertEqual(ctx["related_heading"], "Related blogs")
        self.assertEqual(ctx["related_link_text"], "Read more blogs")

    def test_related_posts_are_scoped_to_own_parent(self):
        """A post under another Blogs page never appears in these related posts."""
        other_blogs = Blogs(title="Press Releases", slug="press-releases-bp")
        self.blogs.get_parent().add_child(instance=other_blogs)
        other_post = Post(title="A Release", slug="a-release-bp", published_at=timezone.now())
        other_blogs.add_child(instance=other_post)

        headings = [card["heading"] for card in self._get_context(self.post)["related_posts"]]
        self.assertNotIn("A Release", headings)
        self.assertIn("No Author Post", headings)

    def test_related_headings_adapt_to_press_releases_parent(self):
        other_blogs = Blogs(title="Press Releases", slug="press-releases-bp2")
        self.blogs.get_parent().add_child(instance=other_blogs)
        release = Post(title="A Release", slug="a-release-bp2", published_at=timezone.now())
        other_blogs.add_child(instance=release)

        ctx = self._get_context(release)
        self.assertEqual(ctx["related_heading"], "Related press releases")
        self.assertEqual(ctx["related_link_text"], "Read more press releases")

    def test_related_intro_uses_parent_related_intro(self):
        self.blogs.related_intro = "Stories from the movement."
        self.blogs.save()
        ctx = self._get_context(Post.objects.get(pk=self.post.pk))
        self.assertEqual(ctx["related_intro"], "Stories from the movement.")

    def test_related_intro_falls_back_to_parent_hero_copy(self):
        self.blogs.related_intro = ""
        self.blogs.hero_copy = "<p>News and insights.</p>"
        self.blogs.save()
        ctx = self._get_context(Post.objects.get(pk=self.post.pk))
        self.assertEqual(ctx["related_intro"], "News and insights.")


class TestPostForm(TestCase):
    """
    PostForm must pre-fill author with the creating user, only for new
    pages.

    Asserts against form["author"].value() (the bound field's actual
    resolved value — what really ends up pre-selected in the rendered
    widget and submitted if untouched), not form.fields["author"].initial.
    Django's Form.get_initial_for_field() checks self.initial (the dict)
    before ever falling back to a field's own .initial attribute, and
    ModelForm.__init__ always populates self.initial from model_to_dict()
    on the instance — including "author": None for a brand new unsaved
    Post — so asserting on fields["author"].initial alone would pass
    even if the pre-fill were silently shadowed and never actually applied.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        home = HomePage(title="Home", slug="home-bpf")
        root.add_child(instance=home)
        cls.blogs = Blogs(title="Blog", slug="blog-bpf")
        home.add_child(instance=cls.blogs)
        cls.user = User.objects.create_user(username="alex")

    def test_author_defaults_to_for_user_on_new_page(self):
        form_class = Post.get_edit_handler().get_form_class()
        form = form_class(for_user=self.user, parent_page=self.blogs, instance=Post())
        self.assertEqual(form["author"].value(), self.user.pk)

    def test_author_not_overridden_on_existing_page(self):
        other_user = User.objects.create_user(username="sam")
        post = Post(title="Existing", slug="existing-bpf", author=other_user)
        self.blogs.add_child(instance=post)

        form_class = Post.get_edit_handler().get_form_class()
        form = form_class(for_user=self.user, parent_page=self.blogs, instance=post)
        self.assertEqual(form["author"].value(), other_user.pk)


class TestPostMeta(TestCase):
    def test_verbose_name(self):
        self.assertEqual(Post._meta.verbose_name, "post")

    def test_verbose_name_plural(self):
        self.assertEqual(Post._meta.verbose_name_plural, "posts")


class TestPostGetCardImage(TestCase):
    """
    Post.get_card_image() is what feeds post_card.html a thumbnail — via
    the override in Post.get_context()/Blogs.get_context() (related posts /
    the Blogs index) and in PageCardsBlock.get_context() — for a post that
    never had an explicit header image set.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        home = HomePage(title="Home", slug="home-cci")
        root.add_child(instance=home)
        cls.blogs = Blogs(title="Blog", slug="blog-cci")
        home.add_child(instance=cls.blogs)

        cls.hero_image = CustomImage.objects.create(
            title="Hero image", file=get_test_image_file(size=(1200, 800))
        )
        cls.body_image = CustomImage.objects.create(
            title="Body image", file=get_test_image_file(size=(1200, 800))
        )

    def _make_post(self, slug, hero_image=None, body=None):
        post = Post(title="Test post", slug=slug, hero_image=hero_image)
        if body is not None:
            post.body = json.dumps(body)
        self.blogs.add_child(instance=post)
        # Re-fetch so `body` is the real deserialized StreamValue a saved
        # page would have, not the raw JSON string just assigned above.
        return Post.objects.get(pk=post.pk)

    def test_explicit_hero_image_wins(self):
        """An explicit header image is used as-is — the body isn't even inspected."""
        body = [
            {
                "type": "image_text",
                "value": {"image": self.body_image.pk, "content": "<h2>Body</h2>"},
                "id": "11111111-1111-1111-1111-111111111111",
            }
        ]
        post = self._make_post("hero-wins", hero_image=self.hero_image, body=body)
        self.assertEqual(post.get_card_image(), self.hero_image)

    def test_falls_back_to_first_image_in_body(self):
        """No header image: the first image found in the body is used instead."""
        body = [
            {"type": "text", "value": "<p>No image here.</p>", "id": "22222222-2222-2222-2222-222222222222"},
            {
                "type": "image_text",
                "value": {"image": self.body_image.pk, "content": "<h2>Body</h2>"},
                "id": "33333333-3333-3333-3333-333333333333",
            },
        ]
        post = self._make_post("body-fallback", hero_image=None, body=body)
        self.assertEqual(post.get_card_image(), self.body_image)

    def test_finds_image_nested_inside_a_card_grids_list_items(self):
        """The search reaches into a ListBlock item's own `image` field (a CardGridBlock card)."""
        body = [
            {
                "type": "card_grid",
                "value": {
                    "heading": "Grid",
                    "cards": [
                        {
                            "tag": "",
                            "icon": None,
                            "content": "<h3>No image</h3>",
                            "image": None,
                            "link_page": None,
                            "link_url": None,
                            "link_text": "",
                        },
                        {
                            "tag": "",
                            "icon": None,
                            "content": "<h3>Has image</h3>",
                            "image": self.body_image.pk,
                            "link_page": None,
                            "link_url": None,
                            "link_text": "",
                        },
                    ],
                },
                "id": "44444444-4444-4444-4444-444444444444",
            }
        ]
        post = self._make_post("card-grid-fallback", hero_image=None, body=body)
        self.assertEqual(post.get_card_image(), self.body_image)

    def test_none_when_no_image_anywhere(self):
        """No header image and no image in the body degrades to None, not an error."""
        body = [{"type": "text", "value": "<p>Just words.</p>", "id": "55555555-5555-5555-5555-555555555555"}]
        post = self._make_post("no-image", hero_image=None, body=body)
        self.assertIsNone(post.get_card_image())

    def test_none_when_body_is_empty(self):
        post = self._make_post("empty-body", hero_image=None, body=[])
        self.assertIsNone(post.get_card_image())


# ---------------------------------------------------------------------------
# Blogs
# ---------------------------------------------------------------------------


class TestBlogsParentSubpageTypes(WagtailPageTests):
    def test_can_create_under_home_page(self):
        self.assertCanCreateAt(HomePage, Blogs)

    def test_can_not_create_under_blogs(self):
        self.assertCanNotCreateAt(Blogs, Blogs)

    def test_allowed_subpage_types(self):
        self.assertAllowedSubpageTypes(Blogs, [Post])


class TestBlogsGetContext(TestCase):
    """
    Blogs.get_context() must list live/public Post children newest-first by
    published_at, and support narrowing to one category via
    ?category=<slug>.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        home = HomePage(title="Home", slug="home-bip")
        root.add_child(instance=home)
        cls.blogs = Blogs(title="Blog", slug="blog-bip")
        home.add_child(instance=cls.blogs)

        cls.climate = BlogCategory.objects.create(name="Climate", slug="climate")
        cls.justice = BlogCategory.objects.create(name="Justice", slug="justice")

        base_time = timezone.now() - timedelta(days=10)
        cls.posts = []
        for i in range(3):
            post = Post(
                title=f"Post {i}",
                slug=f"post-bip-{i}",
                published_at=base_time + timedelta(days=i),
            )
            cls.blogs.add_child(instance=post)
            cls.posts.append(post)

        # ParentalManyToManyField.add() only updates the in-memory cluster —
        # an explicit save() is needed to persist the M2M rows, same as any
        # other change to an already-saved page instance made outside the
        # normal admin edit-form flow (which always re-saves the whole
        # cluster on submit, so this gotcha never surfaces there).
        cls.posts[0].categories.add(cls.climate)
        cls.posts[0].save()
        cls.posts[1].categories.add(cls.justice)
        cls.posts[1].save()
        cls.posts[2].categories.add(cls.climate, cls.justice)
        cls.posts[2].save()

        cls.draft_post = Post(title="Draft", slug="draft-bip", live=False)
        cls.blogs.add_child(instance=cls.draft_post)

    def _get_context(self, query_string=""):
        request = RequestFactory().get("/", query_string)
        return self.blogs.get_context(request)

    def test_posts_ordered_newest_first(self):
        ctx = self._get_context()
        titles = [p.title for p in ctx["posts"].object_list]
        self.assertEqual(titles, ["Post 2", "Post 1", "Post 0"])

    def test_excludes_non_live_posts(self):
        ctx = self._get_context()
        titles = [p.title for p in ctx["posts"].object_list]
        self.assertNotIn("Draft", titles)

    def test_categories_in_context(self):
        ctx = self._get_context()
        self.assertEqual(set(ctx["categories"]), {self.climate, self.justice})

    def test_no_category_filter_selected_by_default(self):
        ctx = self._get_context()
        self.assertIsNone(ctx["selected_category"])

    def test_category_filter_narrows_posts(self):
        ctx = self._get_context({"category": "justice"})
        titles = {p.title for p in ctx["posts"].object_list}
        self.assertEqual(titles, {"Post 1", "Post 2"})

    def test_category_filter_sets_selected_category(self):
        ctx = self._get_context({"category": "climate"})
        self.assertEqual(ctx["selected_category"], self.climate)

    def test_unknown_category_slug_ignored(self):
        ctx = self._get_context({"category": "nonexistent"})
        self.assertIsNone(ctx["selected_category"])
        self.assertEqual(len(ctx["posts"].object_list), 3)


class TestBlogsPostLabel(TestCase):
    """
    Blogs.post_label drives the "Related …" headings on child posts, so it
    must pluralise the page title without doubling an existing "s".
    """

    def test_singular_title_is_pluralised(self):
        self.assertEqual(Blogs(title="Blog").post_label, "blogs")

    def test_plural_title_is_left_alone(self):
        self.assertEqual(Blogs(title="Press Releases").post_label, "press releases")

    def test_title_ending_in_s_is_left_alone(self):
        self.assertEqual(Blogs(title="News").post_label, "news")


class TestBlogsMeta(TestCase):
    def test_verbose_name(self):
        self.assertEqual(Blogs._meta.verbose_name, "Blogs")

    def test_verbose_name_plural(self):
        self.assertEqual(Blogs._meta.verbose_name_plural, "Blogs")

"""
Tests for concrete page models: HomePage, ContentPage, IndexPage, BlogPage,
BlogIndexPage, PressReleasePage, PressReleaseIndexPage.

WagtailPageTests covers parent/subpage type constraints.
TestCase with RequestFactory covers get_context() behaviour.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.utils import timezone
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTests

from wtrx.models import (
    BlogCategory,
    BlogIndexPage,
    BlogPage,
    ContentPage,
    FormPage,
    HomePage,
    IndexPage,
    ITEMS_PER_PAGE,
    PressReleaseIndexPage,
    PressReleasePage,
)


# ---------------------------------------------------------------------------
# HomePage
# ---------------------------------------------------------------------------


class TestHomePageParentSubpageTypes(WagtailPageTests):
    """HomePage can only be created under the Wagtail root page."""

    def test_can_create_under_root(self):
        self.assertCanCreateAt(Page, HomePage)

    def test_can_not_create_under_home_page(self):
        self.assertCanNotCreateAt(HomePage, HomePage)

    def test_can_not_create_under_content_page(self):
        self.assertCanNotCreateAt(ContentPage, HomePage)

    def test_allowed_subpage_types(self):
        self.assertAllowedSubpageTypes(
            HomePage, [ContentPage, IndexPage, FormPage, BlogIndexPage, PressReleaseIndexPage]
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

    def test_hero_layout_defaults_centered(self):
        ctx = self._get_context(self.home)
        self.assertEqual(ctx["hero"]["layout"], "centered")

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
            "layout",
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
            ContentPage, [ContentPage, IndexPage, FormPage, BlogIndexPage, PressReleaseIndexPage]
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
            "layout",
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
            IndexPage, [ContentPage, IndexPage, FormPage, BlogIndexPage, PressReleaseIndexPage]
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
# BlogPage
# ---------------------------------------------------------------------------


class TestBlogPageParentSubpageTypes(WagtailPageTests):
    def test_can_create_under_blog_index_page(self):
        self.assertCanCreateAt(BlogIndexPage, BlogPage)

    def test_can_not_create_under_home_page(self):
        self.assertCanNotCreateAt(HomePage, BlogPage)

    def test_can_not_create_under_content_page(self):
        self.assertCanNotCreateAt(ContentPage, BlogPage)

    def test_allowed_subpage_types(self):
        self.assertAllowedSubpageTypes(BlogPage, [])


class TestBlogPageGetContext(TestCase):
    """
    BlogPage.get_context() must build a "banner" hero dict (via
    BannerHeroMixin.get_banner_hero_context()) with author/published_at
    folded in on top.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        home = HomePage(title="Home", slug="home-bp")
        root.add_child(instance=home)
        cls.blog_index = BlogIndexPage(title="Blog", slug="blog-bp")
        home.add_child(instance=cls.blog_index)

        cls.user = User.objects.create_user(username="jane", first_name="Jane", last_name="Doe")

        cls.post = BlogPage(
            title="A Post",
            slug="a-post-bp",
            hero_headline="Custom headline",
            author=cls.user,
            published_at=timezone.now(),
        )
        cls.blog_index.add_child(instance=cls.post)

        cls.post_no_author = BlogPage(title="No Author Post", slug="no-author-post-bp")
        cls.blog_index.add_child(instance=cls.post_no_author)

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


class TestBlogPageForm(TestCase):
    """
    BlogPageForm must pre-fill author with the creating user, only for new
    pages.

    Asserts against form["author"].value() (the bound field's actual
    resolved value — what really ends up pre-selected in the rendered
    widget and submitted if untouched), not form.fields["author"].initial.
    Django's Form.get_initial_for_field() checks self.initial (the dict)
    before ever falling back to a field's own .initial attribute, and
    ModelForm.__init__ always populates self.initial from model_to_dict()
    on the instance — including "author": None for a brand new unsaved
    BlogPage — so asserting on fields["author"].initial alone would pass
    even if the pre-fill were silently shadowed and never actually applied.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        home = HomePage(title="Home", slug="home-bpf")
        root.add_child(instance=home)
        cls.blog_index = BlogIndexPage(title="Blog", slug="blog-bpf")
        home.add_child(instance=cls.blog_index)
        cls.user = User.objects.create_user(username="alex")

    def test_author_defaults_to_for_user_on_new_page(self):
        form_class = BlogPage.get_edit_handler().get_form_class()
        form = form_class(for_user=self.user, parent_page=self.blog_index, instance=BlogPage())
        self.assertEqual(form["author"].value(), self.user.pk)

    def test_author_not_overridden_on_existing_page(self):
        other_user = User.objects.create_user(username="sam")
        post = BlogPage(title="Existing", slug="existing-bpf", author=other_user)
        self.blog_index.add_child(instance=post)

        form_class = BlogPage.get_edit_handler().get_form_class()
        form = form_class(for_user=self.user, parent_page=self.blog_index, instance=post)
        self.assertEqual(form["author"].value(), other_user.pk)


class TestBlogPageMeta(TestCase):
    def test_verbose_name(self):
        self.assertEqual(BlogPage._meta.verbose_name, "blog page")

    def test_verbose_name_plural(self):
        self.assertEqual(BlogPage._meta.verbose_name_plural, "blog pages")


# ---------------------------------------------------------------------------
# BlogIndexPage
# ---------------------------------------------------------------------------


class TestBlogIndexPageParentSubpageTypes(WagtailPageTests):
    def test_can_create_under_home_page(self):
        self.assertCanCreateAt(HomePage, BlogIndexPage)

    def test_can_not_create_under_blog_index_page(self):
        self.assertCanNotCreateAt(BlogIndexPage, BlogIndexPage)

    def test_allowed_subpage_types(self):
        self.assertAllowedSubpageTypes(BlogIndexPage, [BlogPage])


class TestBlogIndexPageGetContext(TestCase):
    """
    BlogIndexPage.get_context() must list live/public BlogPage children
    newest-first by published_at, and support narrowing to one category via
    ?category=<slug>.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        home = HomePage(title="Home", slug="home-bip")
        root.add_child(instance=home)
        cls.blog_index = BlogIndexPage(title="Blog", slug="blog-bip")
        home.add_child(instance=cls.blog_index)

        cls.climate = BlogCategory.objects.create(name="Climate", slug="climate")
        cls.justice = BlogCategory.objects.create(name="Justice", slug="justice")

        base_time = timezone.now() - timedelta(days=10)
        cls.posts = []
        for i in range(3):
            post = BlogPage(
                title=f"Post {i}",
                slug=f"post-bip-{i}",
                published_at=base_time + timedelta(days=i),
            )
            cls.blog_index.add_child(instance=post)
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

        cls.draft_post = BlogPage(title="Draft", slug="draft-bip", live=False)
        cls.blog_index.add_child(instance=cls.draft_post)

    def _get_context(self, query_string=""):
        request = RequestFactory().get("/", query_string)
        return self.blog_index.get_context(request)

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


class TestBlogIndexPageMeta(TestCase):
    def test_verbose_name(self):
        self.assertEqual(BlogIndexPage._meta.verbose_name, "blog index page")

    def test_verbose_name_plural(self):
        self.assertEqual(BlogIndexPage._meta.verbose_name_plural, "blog index pages")


# ---------------------------------------------------------------------------
# PressReleasePage
# ---------------------------------------------------------------------------


class TestPressReleasePageParentSubpageTypes(WagtailPageTests):
    def test_can_create_under_press_release_index_page(self):
        self.assertCanCreateAt(PressReleaseIndexPage, PressReleasePage)

    def test_can_not_create_under_home_page(self):
        self.assertCanNotCreateAt(HomePage, PressReleasePage)

    def test_allowed_subpage_types(self):
        self.assertAllowedSubpageTypes(PressReleasePage, [])


class TestPressReleasePageMeta(TestCase):
    def test_verbose_name(self):
        self.assertEqual(PressReleasePage._meta.verbose_name, "press release")

    def test_verbose_name_plural(self):
        self.assertEqual(PressReleasePage._meta.verbose_name_plural, "press releases")


# ---------------------------------------------------------------------------
# PressReleaseIndexPage
# ---------------------------------------------------------------------------


class TestPressReleaseIndexPageParentSubpageTypes(WagtailPageTests):
    def test_can_create_under_home_page(self):
        self.assertCanCreateAt(HomePage, PressReleaseIndexPage)

    def test_allowed_subpage_types(self):
        self.assertAllowedSubpageTypes(PressReleaseIndexPage, [PressReleasePage])


class TestPressReleaseIndexPageGetContext(TestCase):
    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        home = HomePage(title="Home", slug="home-prip")
        root.add_child(instance=home)
        cls.index = PressReleaseIndexPage(title="Press", slug="press-prip")
        home.add_child(instance=cls.index)

        base_time = timezone.now() - timedelta(days=5)
        cls.releases = []
        for i in range(2):
            release = PressReleasePage(
                title=f"Release {i}",
                slug=f"release-prip-{i}",
                published_at=base_time + timedelta(days=i),
            )
            cls.index.add_child(instance=release)
            cls.releases.append(release)

    def _get_context(self):
        request = RequestFactory().get("/")
        return self.index.get_context(request)

    def test_releases_ordered_newest_first(self):
        ctx = self._get_context()
        titles = [r.title for r in ctx["releases"].object_list]
        self.assertEqual(titles, ["Release 1", "Release 0"])

    def test_paginator_in_context(self):
        ctx = self._get_context()
        self.assertIn("paginator", ctx)


class TestPressReleaseIndexPageMeta(TestCase):
    def test_verbose_name(self):
        self.assertEqual(
            PressReleaseIndexPage._meta.verbose_name, "press release index page"
        )

    def test_verbose_name_plural(self):
        self.assertEqual(
            PressReleaseIndexPage._meta.verbose_name_plural, "press release index pages"
        )

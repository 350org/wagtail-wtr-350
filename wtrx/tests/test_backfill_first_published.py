from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from wagtail.models import Page

from wtrx.models import Blogs, HomePage, Post


class BackfillFirstPublishedTest(TestCase):
    """
    Imported content arrives live but with no `first_published_at` -- Wagtail
    only sets that on an admin publish. Ordering by it then sorts on mostly-NULL
    data, and PostgreSQL puts NULLs first under DESC, so genuinely recent pages
    sink below every imported one (PageCardsBlock is the visible casualty).
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        home = HomePage(title="Home", slug="home-bf")
        root.add_child(instance=home)
        cls.blogs = Blogs(title="Blog", slug="blog-bf")
        home.add_child(instance=cls.blogs)
        cls.now = timezone.now()

    def _post(self, slug, published_at, first_published_at=None):
        post = Post(title=slug, slug=slug, published_at=published_at)
        self.blogs.add_child(instance=post)
        # add_child() saves, so clear/set the field afterwards to model both an
        # imported page and one published through the admin.
        Page.objects.filter(pk=post.pk).update(first_published_at=first_published_at)
        return Post.objects.get(pk=post.pk)

    def _run(self, **kwargs):
        out = StringIO()
        call_command("backfill_first_published", stdout=out, **kwargs)
        return out.getvalue()

    def test_backfills_from_the_editorial_publication_date(self):
        post = self._post("imported", self.now)
        self.assertIsNone(post.first_published_at)

        self._run()

        post.refresh_from_db()
        self.assertEqual(post.first_published_at, post.published_at)

    def test_leaves_an_existing_date_alone(self):
        already = self.now - timedelta(days=30)
        post = self._post("published-properly", self.now, first_published_at=already)

        self._run()

        post.refresh_from_db()
        self.assertEqual(post.first_published_at, already)

    def test_dry_run_writes_nothing(self):
        post = self._post("imported", self.now)

        output = self._run(dry_run=True)

        post.refresh_from_db()
        self.assertIsNone(post.first_published_at)
        self.assertIn("Would update", output)

    def test_a_recent_page_outranks_imported_ones_afterwards(self):
        """The behaviour the backfill exists to restore."""
        self._post("older-import", self.now - timedelta(days=10))
        newest = self._post("newest", self.now - timedelta(days=1))

        self._run()

        ordered = self.blogs.get_children().live().order_by("-first_published_at")
        self.assertEqual(ordered.first().pk, newest.pk)

"""
Tests for the multilingual setup: one page tree per language under Root, each
served under its own URL prefix (`/pt/...`), with English unprefixed.

See settings/base.py WAGTAIL_CONTENT_LANGUAGES and the `language_links` /
`page_translation_alternates` tags in wtrx/templatetags/wtrx_tags.py.
"""

import json
from io import StringIO

from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.core.management.base import CommandError
from django.template import Context, Template
from django.urls import reverse
from django.test import Client, RequestFactory, TestCase
from django.utils import translation
from wagtail.blocks import CharBlock, RichTextBlock
from wagtail.contrib.redirects.models import Redirect
from wagtail.models import Locale, Page, Site
from wagtail_localize.segments.extract import StreamFieldSegmentExtractor

from wtrx.models import ContentPage, HomePage


def _english():
    return Locale.objects.get(language_code="en")


def _locale(code):
    locale, _created = Locale.objects.get_or_create(language_code=code)
    return locale


class TestBootstrapLocales(TestCase):
    """`manage.py bootstrap_locales` is how an environment gets its Locale rows."""

    def test_creates_every_configured_language_and_is_idempotent(self):
        call_command("bootstrap_locales", stdout=StringIO())
        codes = set(Locale.objects.values_list("language_code", flat=True))
        self.assertEqual(codes, {"en", "pt", "es", "fr", "de", "id"})

        # A second run must not create duplicates or raise.
        call_command("bootstrap_locales", stdout=StringIO())
        self.assertEqual(Locale.objects.count(), 6)

    def test_dry_run_writes_nothing(self):
        before = Locale.objects.count()
        call_command("bootstrap_locales", "--dry-run", stdout=StringIO())
        self.assertEqual(Locale.objects.count(), before)


class TestIdentifierBlocksAreNotTranslatable(TestCase):
    """
    Identifier fields must never reach a translator.

    An ActionKit form shortname or an in-page anchor is a machine identifier,
    not prose: translating one breaks the form fetch or the anchor link
    silently. `IdentifierBlock` opts those fields out of wagtail-localize's
    segment extraction; everything else in the same block stays translatable.
    """

    def _extract(self, raw):
        field = ContentPage._meta.get_field("body")
        value = field.to_python(json.dumps(raw))
        segments = StreamFieldSegmentExtractor(
            field, include_overridables=True
        ).handle_stream_block(value)
        return [segment.path for segment in segments]

    def _block_value(self, block_name, **overrides):
        """A full struct value — wagtail-localize rejects missing (None) children."""
        field = ContentPage._meta.get_field("body")
        block = field.stream_block.child_blocks[block_name]
        value = {
            name: ""
            for name, child in block.child_blocks.items()
            if isinstance(child, (CharBlock, RichTextBlock))
        }
        value.update(overrides)
        return {"type": block_name, "id": f"{block_name}-1", "value": value}

    def test_actionkit_identifiers_are_excluded_but_prose_is_not(self):
        paths = self._extract(
            [
                self._block_value(
                    "signup_actionkit",
                    eyebrow="Join us",
                    content="<p>Sign the petition</p>",
                    short_form_id="petition_climate_2026",
                    anchor_id="signup-form",
                )
            ]
        )
        self.assertIn("signup_actionkit-1.eyebrow", paths)
        self.assertIn("signup_actionkit-1.content", paths)
        self.assertNotIn("signup_actionkit-1.short_form_id", paths)
        self.assertNotIn("signup_actionkit-1.anchor_id", paths)

    def test_button_anchor_is_excluded_but_label_is_not(self):
        paths = self._extract(
            [self._block_value("button", text="Donate now", anchor="give-section")]
        )
        self.assertIn("button-1.text", paths)
        self.assertNotIn("button-1.anchor", paths)

    def test_fundraiseup_designation_id_is_excluded(self):
        paths = self._extract(
            [self._block_value("donate_fundraiseup", designation_id="CLIMATE_FUND")]
        )
        self.assertNotIn("donate_fundraiseup-1.designation_id", paths)


class TestLocalisedServing(TestCase):
    """Each language tree serves under its own prefix; English stays at /."""

    @classmethod
    def setUpTestData(cls):
        cls.pt = _locale("pt")
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-i18n", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

        cls.english_page = ContentPage(title="About", slug="about", locale=_english())
        cls.home.add_child(instance=cls.english_page)

        # The Portuguese tree: a translation of Home, with its own child.
        cls.home_pt = cls.home.copy_for_translation(cls.pt)
        cls.home_pt.title = "Início"
        cls.home_pt.save_revision().publish()
        cls.portuguese_page = ContentPage(
            title="Sobre", slug="sobre", locale=cls.pt
        )
        cls.home_pt.add_child(instance=cls.portuguese_page)

    def setUp(self):
        self.client = Client()

    def test_portuguese_page_serves_under_its_language_prefix(self):
        response = self.client.get("/brasil/sobre/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="pt"')

    def test_english_page_keeps_unprefixed_url_and_english_lang(self):
        """Also guards against language leaking between requests in a process."""
        self.client.get("/brasil/sobre/")
        response = self.client.get("/about/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="en"')

    def test_english_page_is_not_reachable_under_a_language_prefix(self):
        """`/brasil/about/` would be an English page duplicated at a second URL."""
        self.assertEqual(self.client.get("/brasil/about/").status_code, 404)

    def test_new_child_page_inherits_its_parent_language(self):
        child = ContentPage(title="Equipe", slug="equipe")
        self.portuguese_page.add_child(instance=child)
        self.assertEqual(child.locale, self.pt)

    def test_preview_renders_in_the_pages_own_language(self):
        """
        Preview is requested from an admin URL outside i18n_patterns, so
        without BasePage.serve_preview()'s override the chrome would render in
        the editor's language instead of the page's.
        """
        request = RequestFactory().get("/admin/pages/1/edit/preview/")
        request.user = AnonymousUser()
        with translation.override("en"):
            response = self.portuguese_page.serve_preview(request, "")
            self.assertContains(response, 'lang="pt"')
            # The override is scoped: it must not leak past the call.
            self.assertEqual(translation.get_language(), "en")


class TestLanguageLinks(TestCase):
    """The front-end switcher links to real pages, not to set_language."""

    @classmethod
    def setUpTestData(cls):
        cls.pt = _locale("pt")
        cls.fr = _locale("fr")
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-links", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

        cls.home_pt = cls.home.copy_for_translation(cls.pt)
        cls.home_pt.save_revision().publish()
        cls.home_fr = cls.home.copy_for_translation(cls.fr)
        cls.home_fr.save_revision().publish()

        cls.about = ContentPage(title="About", slug="about-links", locale=_english())
        cls.home.add_child(instance=cls.about)
        cls.about_pt = cls.about.copy_for_translation(cls.pt)
        cls.about_pt.slug = "sobre-links"
        cls.about_pt.save_revision().publish()

    def _render(self, template_string, page):
        request = RequestFactory().get("/")
        return Template("{% load wtrx_tags %}" + template_string).render(
            Context({"page": page, "request": request})
        )

    def test_links_to_a_real_translation_when_one_exists(self):
        output = self._render(
            "{% language_links as links %}{% for l in links %}{{ l.code }}:{{ l.url }} {% endfor %}",
            self.about,
        )
        self.assertIn("pt:/brasil/sobre-links/", output)

    def test_falls_back_to_the_language_home_when_untranslated(self):
        """A French visitor should reach the French site, not a 404."""
        output = self._render(
            "{% language_links as links %}{% for l in links %}{{ l.code }}:{{ l.url }} {% endfor %}",
            self.about,
        )
        self.assertIn("fr:/france/", output)

    def test_current_language_is_marked_and_not_linked(self):
        output = self._render(
            "{% language_links as links %}{% for l in links %}{{ l.code }}:{{ l.is_current }} {% endfor %}",
            self.about,
        )
        self.assertIn("en:True", output)
        self.assertIn("pt:False", output)


class TestTranslationAlternates(TestCase):
    """hreflang alternates are emitted only for genuinely linked pages."""

    @classmethod
    def setUpTestData(cls):
        cls.pt = _locale("pt")
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-alt", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

        cls.home_pt = cls.home.copy_for_translation(cls.pt)
        cls.home_pt.save_revision().publish()

        cls.about = ContentPage(title="About", slug="about-alt", locale=_english())
        cls.home.add_child(instance=cls.about)
        cls.about_pt = cls.about.copy_for_translation(cls.pt)
        cls.about_pt.save_revision().publish()

        cls.untranslated = ContentPage(
            title="Press", slug="press-alt", locale=_english()
        )
        cls.home.add_child(instance=cls.untranslated)

    def _codes(self, page):
        request = RequestFactory().get("/")
        output = Template(
            "{% load wtrx_tags %}{% page_translation_alternates as alts %}"
            "{% for a in alts %}{{ a.code }} {% endfor %}"
        ).render(Context({"page": page, "request": request}))
        return output.split()

    def test_emits_each_language_plus_x_default(self):
        self.assertEqual(sorted(self._codes(self.about)), ["en", "pt", "x-default"])

    def test_emits_nothing_for_an_untranslated_page(self):
        """A lone self-referencing alternate tells search engines nothing."""
        self.assertEqual(self._codes(self.untranslated), [])


class TestLocalizedNavigationLinks(TestCase):
    """
    Navigation/footer links are chosen once in site settings (one row per Site,
    shared by every language tree), so they hold the English page. The
    `localized` filter resolves them to the current language's version.
    """

    @classmethod
    def setUpTestData(cls):
        cls.pt = _locale("pt")
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-nav", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

        cls.home_pt = cls.home.copy_for_translation(cls.pt)
        cls.home_pt.save_revision().publish()

        cls.translated = ContentPage(
            title="About", slug="about-nav", locale=_english()
        )
        cls.home.add_child(instance=cls.translated)
        cls.translated_pt = cls.translated.copy_for_translation(cls.pt)
        cls.translated_pt.slug = "sobre-nav"
        cls.translated_pt.save_revision().publish()

        cls.untranslated = ContentPage(
            title="Press", slug="press-nav", locale=_english()
        )
        cls.home.add_child(instance=cls.untranslated)

    def _url(self, page):
        return Template(
            "{% load wagtailcore_tags wtrx_tags %}{% pageurl page|localized %}"
        ).render(Context({"page": page, "request": RequestFactory().get("/")}))

    def test_link_resolves_to_the_translation_in_that_language(self):
        with translation.override("pt"):
            self.assertEqual(self._url(self.translated), "/brasil/sobre-nav/")

    def test_untranslated_link_falls_back_to_the_source_page(self):
        """Better a link to the English page than a dead link."""
        with translation.override("pt"):
            self.assertEqual(self._url(self.untranslated), "/press-nav/")

    def test_english_pages_are_unaffected(self):
        with translation.override("en"):
            self.assertEqual(self._url(self.translated), "/about-nav/")


class TestConvertSectionToLocale(TestCase):
    """
    `convert_section_to_locale` turns an existing English section into a
    language tree in place — the operation the admin cannot do, since
    `Page.locale` is not editable and `can_move_to()` blocks cross-locale
    parents.
    """

    @classmethod
    def setUpTestData(cls):
        cls.pt = _locale("pt")
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-conv", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

        # Slug deliberately unlike pt's mapped prefix, so conversion moves URLs
        # and redirects are needed. The real sites are the other case, covered
        # by test_no_redirects_needed_when_the_url_does_not_change.
        cls.section = HomePage(title="Brasil", slug="brasil-regional", locale=_english())
        cls.home.add_child(instance=cls.section)
        cls.child = ContentPage(title="Sobre", slug="sobre", locale=_english())
        cls.section.add_child(instance=cls.child)
        cls.child.save_revision()

        # An English page that must be left alone.
        cls.bystander = ContentPage(title="About", slug="about-conv", locale=_english())
        cls.home.add_child(instance=cls.bystander)

    def _convert(self, *args):
        out = StringIO()
        call_command("convert_section_to_locale", *args, stdout=out)
        return out.getvalue()

    def test_section_moves_to_root_and_serves_under_the_language_prefix(self):
        self._convert(str(self.section.pk), "pt")
        section = Page.objects.get(pk=self.section.pk)
        self.assertEqual(section.depth, 2)
        self.assertEqual(section.locale, self.pt)
        self.assertEqual(section.url, "/brasil/")
        self.assertEqual(Page.objects.get(pk=self.child.pk).url, "/brasil/sobre/")

    def test_every_descendant_is_retagged(self):
        self._convert(str(self.section.pk), "pt")
        self.assertEqual(Page.objects.get(pk=self.child.pk).locale, self.pt)
        self.assertEqual(Page.objects.get(pk=self.bystander.pk).locale, _english())

    def test_section_root_becomes_the_site_roots_counterpart(self):
        """That shared key is what gives the tree a URL at all."""
        self._convert(str(self.section.pk), "pt")
        section = Page.objects.get(pk=self.section.pk)
        self.assertEqual(section.translation_key, self.home.translation_key)
        self.assertEqual(self.home.get_translation(self.pt).pk, section.pk)

    def test_descendants_get_their_own_identity(self):
        """They are this language's pages, not translations of English ones."""
        self._convert(str(self.section.pk), "pt")
        child = Page.objects.get(pk=self.child.pk)
        self.assertNotEqual(child.translation_key, self.child.translation_key)
        self.assertEqual(child.get_translations().count(), 0)

    def test_stored_revisions_are_retagged_too(self):
        """Otherwise reverting an old revision silently restores the old locale."""
        self._convert(str(self.section.pk), "pt")
        child = Page.objects.get(pk=self.child.pk)
        revisions = list(child.revisions.all())
        self.assertTrue(revisions)
        for revision in revisions:
            self.assertEqual(revision.content["locale"], self.pt.pk)
            self.assertEqual(revision.content["translation_key"], str(child.translation_key))

    def test_old_urls_redirect_to_the_moved_pages(self):
        """
        Wagtail's own move-time autocreation cannot cover this: mid-conversion
        the page is still English and at Root, where it has no URL yet.
        """
        self._convert(str(self.section.pk), "pt")
        root_redirect = Redirect.objects.filter(old_path="/brasil-regional").first()
        self.assertIsNotNone(root_redirect)
        self.assertEqual(root_redirect.redirect_page.pk, self.section.pk)
        self.assertTrue(root_redirect.is_permanent)
        self.assertEqual(Client().get("/brasil-regional/").status_code, 301)
        self.assertEqual(Client().get("/brasil-regional/sobre/").status_code, 301)

    def test_no_redirects_flag_skips_them(self):
        """
        Asserted on the command's own output, not on the redirect table:
        Wagtail's move handler writes rows of its own here, and whether it
        manages to is exactly what cannot be relied on (it wrote none at all
        for the real 885-page section).
        """
        output = self._convert(str(self.section.pk), "pt", "--no-redirects")
        self.assertIn("created 0 redirects", output)

    def test_dry_run_writes_nothing(self):
        self._convert(str(self.section.pk), "pt", "--dry-run")
        section = Page.objects.get(pk=self.section.pk)
        self.assertEqual(section.locale, _english())
        self.assertEqual(section.depth, 3)

    def test_refuses_when_the_language_already_has_a_site_root_counterpart(self):
        self._convert(str(self.section.pk), "pt")
        other = HomePage(title="Outro", slug="outro", locale=_english())
        self.home.add_child(instance=other)
        with self.assertRaises(CommandError):
            self._convert(str(other.pk), "pt")

    def test_no_redirects_needed_when_the_url_does_not_change(self):
        """
        A section whose slug already matches its language's mapped prefix
        (`/brasil/` for pt) keeps every URL it had, so conversion is invisible
        from outside and there is nothing to redirect.
        """
        already_named = HomePage(title="Brasil", slug="brasil", locale=_english())
        self.home.add_child(instance=already_named)
        child = ContentPage(title="Nos", slug="nos", locale=_english())
        already_named.add_child(instance=child)
        before = Page.objects.get(pk=child.pk).url

        output = self._convert(str(already_named.pk), "pt")

        self.assertEqual(Page.objects.get(pk=child.pk).url, before)
        self.assertIn("created 0 redirects", output)

    def test_refuses_to_convert_the_site_root(self):
        with self.assertRaises(CommandError):
            self._convert(str(self.home.pk), "pt")


class TestAliasPagesAreNotAdvertisedAsTranslations(TestCase):
    """
    wagtail-localize creates an alias parent whenever a translation needs an
    untranslated one. It mirrors its source rather than translating it, so it
    must not appear in hreflang.
    """

    @classmethod
    def setUpTestData(cls):
        cls.fr = _locale("fr")
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-alias", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()
        cls.alias = cls.home.copy_for_translation(cls.fr, alias=True)

    def test_alias_is_omitted_from_hreflang(self):
        self.assertIsNotNone(Page.objects.get(pk=self.alias.pk).alias_of_id)
        output = Template(
            "{% load wtrx_tags %}{% page_translation_alternates as alts %}"
            "{% for a in alts %}{{ a.code }} {% endfor %}"
        ).render(Context({"page": self.home, "request": RequestFactory().get("/")}))
        self.assertEqual(output.split(), [])


class TestNamedLanguageUrlPrefixes(TestCase):
    """
    A language tree serves under the segment WTRX_LANGUAGE_URL_PREFIXES maps
    it to (`/brasil/`, not `/pt/`), so the country sites keep the URLs they
    already have instead of moving behind redirects. See wtrx/i18n.py.
    """

    @classmethod
    def setUpTestData(cls):
        cls.pt = _locale("pt")
        cls.es = _locale("es")
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-prefix", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

        cls.english_page = ContentPage(title="About", slug="about-prefix", locale=_english())
        cls.home.add_child(instance=cls.english_page)

        cls.home_pt = cls.home.copy_for_translation(cls.pt)
        cls.home_pt.save_revision().publish()
        cls.pt_page = ContentPage(title="Sobre", slug="sobre-prefix", locale=cls.pt)
        cls.home_pt.add_child(instance=cls.pt_page)

        cls.home_es = cls.home.copy_for_translation(cls.es)
        cls.home_es.save_revision().publish()

    def test_mapped_language_serves_under_its_name(self):
        response = Client().get("/brasil/sobre-prefix/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="pt"')

    def test_mapped_language_is_not_also_served_under_its_code(self):
        """One canonical URL per tree — no duplicate for search engines."""
        self.assertEqual(Client().get("/pt/sobre-prefix/").status_code, 404)

    def test_unmapped_language_keeps_its_code(self):
        """A language used for occasional translations needs no named prefix."""
        self.assertEqual(Page.objects.get(pk=self.home_es.pk).url, "/es/")

    def test_default_language_stays_unprefixed(self):
        self.assertEqual(Page.objects.get(pk=self.english_page.pk).url, "/about-prefix/")
        self.assertContains(Client().get("/about-prefix/"), 'lang="en"')

    def test_page_urls_are_generated_with_the_mapped_prefix(self):
        self.assertEqual(Page.objects.get(pk=self.pt_page.pk).url, "/brasil/sobre-prefix/")

    def test_reverse_uses_the_mapped_prefix(self):
        """
        The canary for `LocalePrefixPattern`, which is not public Django API:
        if an upgrade changes how the prefix is built, this fails here rather
        than silently on the site.
        """
        with translation.override("pt"):
            self.assertEqual(reverse("search"), "/brasil/search/")
        with translation.override("es"):
            self.assertEqual(reverse("search"), "/es/search/")
        with translation.override("en"):
            self.assertEqual(reverse("search"), "/search/")

    def test_prefixed_responses_do_not_vary_on_accept_language(self):
        """
        A prefixed URL names its own language, so it stays cacheable per-URL.
        Unprefixed English still varies, as Django does by default.
        """
        self.assertNotIn(
            "Accept-Language", Client().get("/brasil/sobre-prefix/").get("Vary", "")
        )
        self.assertIn("Accept-Language", Client().get("/about-prefix/").get("Vary", ""))

    def test_content_language_header_matches_the_prefix(self):
        self.assertEqual(
            Client().get("/brasil/sobre-prefix/")["Content-Language"], "pt"
        )

"""
Tests for the multilingual setup: one page tree per language under Root, each
served under its own URL prefix (`/pt/...`), with English unprefixed.

See settings/base.py WAGTAIL_CONTENT_LANGUAGES and the `language_links` /
`page_translation_alternates` tags in wtrx/templatetags/wtrx_tags.py.
"""

import json
import re
from io import StringIO
from urllib.parse import urlparse

from django.conf import settings
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
from wagtail.search.backends import get_search_backend
from wagtail_localize.segments.extract import StreamFieldSegmentExtractor

from wtrx.i18n import language_from_url_prefix, url_prefix_for_language
from wtrx.models import ContentPage, HomePage


def _english():
    return Locale.objects.get(language_code="en")


def _locale(code):
    locale, _created = Locale.objects.get_or_create(language_code=code)
    return locale


class TestBootstrapLocales(TestCase):
    """
    `manage.py bootstrap_locales` is how an environment gets its Locale rows.

    It creates the languages it is given, not every one in settings: the
    settings list offers every language any 350 site might need, and a stray
    Locale row shows up in every "translate into" menu and cannot be removed
    once a page uses it (`on_delete=PROTECT`).
    """

    def test_creates_only_the_languages_it_is_given(self):
        call_command("bootstrap_locales", "pt-br", "fr-fr", stdout=StringIO())
        codes = set(Locale.objects.values_list("language_code", flat=True))
        self.assertEqual(codes, {"en", "pt-br", "fr-fr"})

    def test_is_idempotent(self):
        call_command("bootstrap_locales", "pt-br", stdout=StringIO())
        call_command("bootstrap_locales", "pt-br", stdout=StringIO())
        self.assertEqual(Locale.objects.filter(language_code="pt-br").count(), 1)

    def test_no_arguments_reports_without_writing(self):
        before = Locale.objects.count()
        out = StringIO()
        call_command("bootstrap_locales", stdout=out)
        self.assertEqual(Locale.objects.count(), before)
        self.assertIn("Available but not created", out.getvalue())

    def test_all_flag_creates_every_configured_language(self):
        call_command("bootstrap_locales", "--all", stdout=StringIO())
        self.assertEqual(
            Locale.objects.count(), len(settings.WAGTAIL_CONTENT_LANGUAGES)
        )

    def test_unconfigured_language_is_refused(self):
        """A Locale for a language settings doesn't offer has no way to serve."""
        with self.assertRaises(CommandError):
            call_command("bootstrap_locales", "kl", stdout=StringIO())

    def test_dry_run_writes_nothing(self):
        before = Locale.objects.count()
        call_command("bootstrap_locales", "pt-br", "--dry-run", stdout=StringIO())
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
        cls.es = _locale("es")
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-i18n", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

        cls.english_page = ContentPage(title="About", slug="about", locale=_english())
        cls.home.add_child(instance=cls.english_page)

        # The Portuguese tree: a translation of Home, with its own child.
        cls.home_es = cls.home.copy_for_translation(cls.es)
        cls.home_es.title = "Inicio"
        cls.home_es.save_revision().publish()
        cls.spanish_page = ContentPage(
            title="Sobre", slug="sobre", locale=cls.es
        )
        cls.home_es.add_child(instance=cls.spanish_page)

    def setUp(self):
        self.client = Client()

    def test_translated_page_serves_under_its_language_prefix(self):
        response = self.client.get("/es/sobre/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="es"')

    def test_english_page_keeps_unprefixed_url_and_english_lang(self):
        """Also guards against language leaking between requests in a process."""
        self.client.get("/es/sobre/")
        response = self.client.get("/about/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="en"')

    def test_english_page_is_not_reachable_under_a_language_prefix(self):
        """`/es/about/` would be an English page duplicated at a second URL."""
        self.assertEqual(self.client.get("/es/about/").status_code, 404)

    def test_new_child_page_inherits_its_parent_language(self):
        child = ContentPage(title="Equipe", slug="equipe")
        self.spanish_page.add_child(instance=child)
        self.assertEqual(child.locale, self.es)

    def test_preview_renders_in_the_pages_own_language(self):
        """
        Preview is requested from an admin URL outside i18n_patterns, so
        without BasePage.serve_preview()'s override the chrome would render in
        the editor's language instead of the page's.
        """
        request = RequestFactory().get("/admin/pages/1/edit/preview/")
        request.user = AnonymousUser()
        with translation.override("en"):
            response = self.spanish_page.serve_preview(request, "")
            self.assertContains(response, 'lang="es"')
            # The override is scoped: it must not leak past the call.
            self.assertEqual(translation.get_language(), "en")


class TestLanguageLinks(TestCase):
    """The front-end switcher links to real pages, not to set_language."""

    @classmethod
    def setUpTestData(cls):
        cls.es = _locale("es")
        cls.fr = _locale("fr-fr")
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-links", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

        cls.home_es = cls.home.copy_for_translation(cls.es)
        cls.home_es.save_revision().publish()
        cls.home_fr = cls.home.copy_for_translation(cls.fr)
        cls.home_fr.save_revision().publish()

        cls.about = ContentPage(title="About", slug="about-links", locale=_english())
        cls.home.add_child(instance=cls.about)
        cls.about_es = cls.about.copy_for_translation(cls.es)
        cls.about_es.slug = "sobre-links"
        cls.about_es.save_revision().publish()

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
        self.assertIn("es:/es/sobre-links/", output)

    def test_falls_back_to_the_language_home_when_untranslated(self):
        """A French visitor should reach the French site, not a 404."""
        output = self._render(
            "{% language_links as links %}{% for l in links %}{{ l.code }}:{{ l.url }} {% endfor %}",
            self.about,
        )
        self.assertIn("fr-fr:/france/", output)

    def test_current_language_is_marked_and_not_linked(self):
        output = self._render(
            "{% language_links as links %}{% for l in links %}{{ l.code }}:{{ l.is_current }} {% endfor %}",
            self.about,
        )
        self.assertIn("en:True", output)
        self.assertIn("es:False", output)


class TestTranslationAlternates(TestCase):
    """hreflang alternates are emitted only for genuinely linked pages."""

    @classmethod
    def setUpTestData(cls):
        cls.es = _locale("es")
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-alt", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

        cls.home_es = cls.home.copy_for_translation(cls.es)
        cls.home_es.save_revision().publish()

        cls.about = ContentPage(title="About", slug="about-alt", locale=_english())
        cls.home.add_child(instance=cls.about)
        cls.about_es = cls.about.copy_for_translation(cls.es)
        cls.about_es.save_revision().publish()

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
        self.assertEqual(sorted(self._codes(self.about)), ["en", "es", "x-default"])

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
        cls.es = _locale("es")
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-nav", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

        cls.home_es = cls.home.copy_for_translation(cls.es)
        cls.home_es.save_revision().publish()

        cls.translated = ContentPage(
            title="About", slug="about-nav", locale=_english()
        )
        cls.home.add_child(instance=cls.translated)
        cls.translated_es = cls.translated.copy_for_translation(cls.es)
        cls.translated_es.slug = "sobre-nav"
        cls.translated_es.save_revision().publish()

        cls.untranslated = ContentPage(
            title="Press", slug="press-nav", locale=_english()
        )
        cls.home.add_child(instance=cls.untranslated)

    def _url(self, page):
        return Template(
            "{% load wagtailcore_tags wtrx_tags %}{% pageurl page|localized %}"
        ).render(Context({"page": page, "request": RequestFactory().get("/")}))

    def test_link_resolves_to_the_translation_in_that_language(self):
        with translation.override("es"):
            self.assertEqual(self._url(self.translated), "/es/sobre-nav/")

    def test_untranslated_link_falls_back_to_the_source_page(self):
        """Better a link to the English page than a dead link."""
        with translation.override("es"):
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
        cls.es = _locale("es")
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
        self._convert(str(self.section.pk), "es")
        section = Page.objects.get(pk=self.section.pk)
        self.assertEqual(section.depth, 2)
        self.assertEqual(section.locale, self.es)
        self.assertEqual(section.url, "/es/")
        self.assertEqual(Page.objects.get(pk=self.child.pk).url, "/es/sobre/")

    def test_every_descendant_is_retagged(self):
        self._convert(str(self.section.pk), "es")
        self.assertEqual(Page.objects.get(pk=self.child.pk).locale, self.es)
        self.assertEqual(Page.objects.get(pk=self.bystander.pk).locale, _english())

    def test_section_root_becomes_the_site_roots_counterpart(self):
        """That shared key is what gives the tree a URL at all."""
        self._convert(str(self.section.pk), "es")
        section = Page.objects.get(pk=self.section.pk)
        self.assertEqual(section.translation_key, self.home.translation_key)
        self.assertEqual(self.home.get_translation(self.es).pk, section.pk)

    def test_descendants_get_their_own_identity(self):
        """They are this language's pages, not translations of English ones."""
        self._convert(str(self.section.pk), "es")
        child = Page.objects.get(pk=self.child.pk)
        self.assertNotEqual(child.translation_key, self.child.translation_key)
        self.assertEqual(child.get_translations().count(), 0)

    def test_stored_revisions_are_retagged_too(self):
        """Otherwise reverting an old revision silently restores the old locale."""
        self._convert(str(self.section.pk), "es")
        child = Page.objects.get(pk=self.child.pk)
        revisions = list(child.revisions.all())
        self.assertTrue(revisions)
        for revision in revisions:
            self.assertEqual(revision.content["locale"], self.es.pk)
            self.assertEqual(revision.content["translation_key"], str(child.translation_key))

    def test_old_urls_redirect_to_the_moved_pages(self):
        """
        Wagtail's own move-time autocreation cannot cover this: mid-conversion
        the page is still English and at Root, where it has no URL yet.
        """
        self._convert(str(self.section.pk), "es")
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
        output = self._convert(str(self.section.pk), "es", "--no-redirects")
        self.assertIn("created 0 redirects", output)

    def test_dry_run_writes_nothing(self):
        self._convert(str(self.section.pk), "es", "--dry-run")
        section = Page.objects.get(pk=self.section.pk)
        self.assertEqual(section.locale, _english())
        self.assertEqual(section.depth, 3)

    def test_refuses_when_the_language_already_has_a_site_root_counterpart(self):
        self._convert(str(self.section.pk), "es")
        other = HomePage(title="Outro", slug="outro", locale=_english())
        self.home.add_child(instance=other)
        with self.assertRaises(CommandError):
            self._convert(str(other.pk), "es")

    def test_a_real_run_says_to_restart_the_workers(self):
        """
        Wagtail's site root path cache is per-process and an hour long, so
        clearing it inside the command reaches only the command's own process.
        A worker still holding the old copy matches none of the moved pages'
        url_paths and returns `url = None` for all of them -- empty nav links,
        sitemap entries and canonical tags -- while still serving the pages
        fine, which is what makes it easy to miss.
        """
        output = self._convert(str(self.section.pk), "es")

        self.assertIn("Restart the application workers", output)

    def test_a_dry_run_does_not(self):
        output = self._convert(str(self.section.pk), "es", "--dry-run")

        self.assertNotIn("Restart the application workers", output)

    def test_dry_run_reports_the_mapped_prefix_not_the_bare_code(self):
        """
        The report has to name the URL the tree will actually serve at.

        pt-br serves at /brasil/, so a report saying `-> /pt-br/` would tell an
        operator that every URL is about to move when in fact none of them are
        — the difference between a routine conversion and one that looks like
        it needs thousands of redirects.
        """
        _locale("pt-br")
        already_named = HomePage(title="Brasil", slug="brasil", locale=_english())
        self.home.add_child(instance=already_named)

        output = self._convert(str(already_named.pk), "pt-br", "--dry-run")

        self.assertIn("-> /brasil/", output)
        self.assertNotIn("-> /pt-br/", output)
        self.assertIn("unchanged", output)

    def test_dry_run_reports_when_urls_do_move(self):
        """The other branch: a slug that is not already the mapped prefix."""
        output = self._convert(str(self.section.pk), "es", "--dry-run")

        self.assertIn("/brasil-regional/ -> /es/", output)
        self.assertNotIn("unchanged", output)

    def test_no_redirects_needed_when_the_url_does_not_change(self):
        """
        A country site converted to its country-variant locale keeps every URL
        it had -- pt-br maps to `brasil`, the slug it already has -- so the
        conversion is invisible from outside and there is nothing to redirect.
        """
        _locale("pt-br")
        already_named = HomePage(title="Brasil", slug="brasil", locale=_english())
        self.home.add_child(instance=already_named)
        child = ContentPage(title="Nos", slug="nos", locale=_english())
        already_named.add_child(instance=child)
        before = Page.objects.get(pk=child.pk).url

        output = self._convert(str(already_named.pk), "pt-br")

        self.assertEqual(Page.objects.get(pk=child.pk).url, before)
        self.assertIn("created 0 redirects", output)

    def test_refuses_to_convert_the_site_root(self):
        with self.assertRaises(CommandError):
            self._convert(str(self.home.pk), "es")


class TestAliasPagesAreNotAdvertisedAsTranslations(TestCase):
    """
    wagtail-localize creates an alias parent whenever a translation needs an
    untranslated one. It mirrors its source rather than translating it, so it
    must not appear in hreflang.
    """

    @classmethod
    def setUpTestData(cls):
        cls.fr = _locale("fr-fr")
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
    A country site serves under the segment WTRX_LANGUAGE_URL_PREFIXES maps
    its locale to (`pt-br` -> `/brasil/`), keeping the URL it already has
    instead of moving behind a redirect. A plain translation locale has no
    mapping and serves under its own code (`/es/`). See wtrx/i18n.py.
    """

    @classmethod
    def setUpTestData(cls):
        cls.pt_br = _locale("pt-br")
        cls.es = _locale("es")
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-prefix", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

        cls.english_page = ContentPage(title="About", slug="about-prefix", locale=_english())
        cls.home.add_child(instance=cls.english_page)

        cls.home_pt_br = cls.home.copy_for_translation(cls.pt_br)
        cls.home_pt_br.save_revision().publish()
        cls.pt_page = ContentPage(title="Sobre", slug="sobre-prefix", locale=cls.pt_br)
        cls.home_pt_br.add_child(instance=cls.pt_page)

        cls.home_es = cls.home.copy_for_translation(cls.es)
        cls.home_es.save_revision().publish()

    def test_mapped_language_serves_under_its_name(self):
        response = Client().get("/brasil/sobre-prefix/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="pt-br"')

    def test_mapped_language_is_not_also_served_under_its_code(self):
        """One canonical URL per tree — no duplicate for search engines."""
        self.assertEqual(Client().get("/pt-br/sobre-prefix/").status_code, 404)

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
        with translation.override("pt-br"):
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
            Client().get("/brasil/sobre-prefix/")["Content-Language"], "pt-br"
        )


class TestCountrySlugScheme(TestCase):
    """
    Every language's URL follows one rule (settings/base.py):

        a country site        -> the country slug             /brasil
        a country translation -> that slug, then the language /brasil/en
        a global language     -> its own code                 /es
        English (the default) -> unprefixed                   /

    A country slug carries no language segment of its own, so /brasil is
    Portuguese and /canada is English. A second language on the same country
    site nests underneath it, which is what the multi-segment prefix support
    in wtrx/i18n.py exists for -- and why longest-prefix-wins matters: both
    `brasil` and `brasil/en` are mapped, and each has to keep its own tree.
    """

    @classmethod
    def setUpTestData(cls):
        cls.pt_br = _locale("pt-br")
        cls.en_br = _locale("en-br")
        cls.fr_ca = _locale("fr-ca")
        cls.es = _locale("es")

        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-scheme", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

        cls.english_page = ContentPage(
            title="About", slug="about-scheme", locale=_english()
        )
        cls.home.add_child(instance=cls.english_page)

        def tree(locale, slug):
            home = cls.home.copy_for_translation(locale)
            home.save_revision().publish()
            page = ContentPage(title=slug, slug=slug, locale=locale)
            home.add_child(instance=page)
            return page

        cls.pt_page = tree(cls.pt_br, "sobre-scheme")
        cls.en_br_page = tree(cls.en_br, "about-brasil")
        cls.fr_ca_page = tree(cls.fr_ca, "a-propos-canada")
        cls.es_page = tree(cls.es, "sobre-global")

    # --- a country site sits at its slug, in its own language ---

    def test_country_site_serves_at_its_slug(self):
        response = Client().get("/brasil/sobre-scheme/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="pt-br"')

    def test_country_site_is_not_also_served_under_its_code(self):
        """One canonical URL per tree."""
        self.assertEqual(Client().get("/pt-br/sobre-scheme/").status_code, 404)

    # --- a translation of a country site nests under that slug ---

    def test_country_translation_nests_under_the_country_slug(self):
        response = Client().get("/brasil/en/about-brasil/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="en-br"')

    def test_canadian_french_nests_under_canada(self):
        response = Client().get("/canada/fr/a-propos-canada/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="fr-ca"')

    def test_the_nested_prefix_does_not_swallow_the_country_site(self):
        """`brasil/en` is mapped too, and must not claim plain `/brasil/`."""
        self.assertEqual(language_from_url_prefix("/brasil/sobre-scheme/"), "pt-br")
        self.assertEqual(language_from_url_prefix("/brasil/en/about-brasil/"), "en-br")

    def test_a_translation_is_not_served_at_its_bare_code(self):
        self.assertEqual(Client().get("/en-br/about-brasil/").status_code, 404)

    # --- a global language keeps its own code ---

    def test_global_language_serves_under_its_code(self):
        response = Client().get("/es/sobre-global/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="es"')

    def test_english_stays_unprefixed(self):
        response = Client().get("/about-scheme/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="en"')

    # --- generated URLs agree with all of the above ---

    def test_page_urls_use_the_scheme(self):
        self.assertEqual(
            Page.objects.get(pk=self.pt_page.pk).url, "/brasil/sobre-scheme/"
        )
        self.assertEqual(
            Page.objects.get(pk=self.en_br_page.pk).url, "/brasil/en/about-brasil/"
        )
        self.assertEqual(
            Page.objects.get(pk=self.fr_ca_page.pk).url,
            "/canada/fr/a-propos-canada/",
        )
        self.assertEqual(
            Page.objects.get(pk=self.es_page.pk).url, "/es/sobre-global/"
        )
        self.assertEqual(
            Page.objects.get(pk=self.english_page.pk).url, "/about-scheme/"
        )

    def test_reverse_uses_the_scheme(self):
        """
        The canary for `LocalePrefixPattern`, which is not public Django API.
        """
        for code, expected in [
            ("pt-br", "/brasil/search/"),
            ("en-br", "/brasil/en/search/"),
            ("fr-ca", "/canada/fr/search/"),
            ("es", "/es/search/"),
            ("en", "/search/"),
        ]:
            with self.subTest(code=code), translation.override(code):
                self.assertEqual(reverse("search"), expected)

    def test_canadian_english_owns_the_canada_slug(self):
        """`/canada/` is en-ca's, which is what makes the section convertible."""
        self.assertEqual(url_prefix_for_language("en-ca"), "canada")


class TestPrefixWithoutALocale(TestCase):
    """
    A language is offered in settings long before it is created, so most mapped
    prefixes have no `Locale` row behind them. Such a prefix must not resolve:
    it would activate a language with no content, `Page.localized` would fall
    back to the English source page, and the English home would be served at a
    second URL — a duplicate for search engines, and in practice a 500.

    This is also what makes a prefix safe to map ahead of the conversion, which
    is how `en-ca` -> `canada` is configured today.
    """

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-uncreated", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

    def test_mapped_prefix_does_not_resolve_without_a_locale(self):
        """`ja` is configured and mapped to `japan`, but is not created here."""
        self.assertFalse(Locale.objects.filter(language_code="ja").exists())
        self.assertEqual(Client().get("/japan/").status_code, 404)

    def test_path_is_not_claimed_for_the_language(self):
        from wtrx.i18n import language_from_url_prefix, url_prefix_for_language

        self.assertIsNone(language_from_url_prefix("/japan/"))

    def test_the_same_prefix_resolves_once_the_locale_exists(self):
        """The guard is about the Locale row, not about the mapping."""
        from wtrx.i18n import language_from_url_prefix, url_prefix_for_language

        _locale("ja")
        self.assertEqual(language_from_url_prefix("/japan/"), "ja")

    def test_an_unmapped_english_path_is_unaffected(self):
        response = Client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="en"')


class TestSearchIsScopedToTheActiveLocale(TestCase):
    """
    Each language is its own page tree, so an unscoped search returns every
    site's content at once — a visitor searching from /brasil/ would get
    French and German pages they cannot read, at URLs outside the site they
    are on. With a single locale this could not happen; it became reachable
    the moment the country sites became language trees.
    """

    @classmethod
    def setUpTestData(cls):
        cls.pt_br = _locale("pt-br")
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-search", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

        # The same distinctive word in both trees.
        cls.english_hit = ContentPage(
            title="Climate elsewhere", slug="climate-en", locale=_english()
        )
        cls.home.add_child(instance=cls.english_hit)

        cls.home_pt = cls.home.copy_for_translation(cls.pt_br)
        cls.home_pt.save_revision().publish()
        cls.pt_hit = ContentPage(
            title="Climate brasileiro", slug="climate-pt", locale=cls.pt_br
        )
        cls.home_pt.add_child(instance=cls.pt_hit)

        # The database backend indexes on a signal that does not fire for pages
        # built in setUpTestData, so without this both searches return nothing
        # and the test would pass for the wrong reason.
        backend = get_search_backend()
        for page in (cls.english_hit, cls.pt_hit):
            backend.add(Page.objects.get(pk=page.pk))

    def _titles(self, url):
        response = Client().get(url, {"query": "Climate"})
        self.assertEqual(response.status_code, 200)
        return [p.title for p in response.context["search_results"]]

    def test_a_country_site_searches_only_its_own_tree(self):
        titles = self._titles("/brasil/search/")
        self.assertIn("Climate brasileiro", titles)
        self.assertNotIn("Climate elsewhere", titles)

    def test_english_search_does_not_return_other_languages(self):
        titles = self._titles("/search/")
        self.assertIn("Climate elsewhere", titles)
        self.assertNotIn("Climate brasileiro", titles)


class TestSitemapCoversEveryLanguageTree(TestCase):
    """
    Wagtail's own sitemap lists `site.root_page.get_descendants()`. Each
    language is its own tree at Root level, so the country sites are siblings
    of the English home rather than descendants — and the stock sitemap drops
    every page in them without erroring. See wtrx/sitemaps.py.
    """

    @classmethod
    def setUpTestData(cls):
        cls.pt_br = _locale("pt-br")
        root = Page.objects.filter(depth=1).first()
        cls.home = HomePage(title="Home", slug="home-sitemap", locale=_english())
        root.add_child(instance=cls.home)
        site = Site.objects.get(is_default_site=True)
        site.root_page = cls.home
        site.save()

        cls.english_page = ContentPage(
            title="About", slug="about-sitemap", locale=_english()
        )
        cls.home.add_child(instance=cls.english_page)

        cls.home_pt = cls.home.copy_for_translation(cls.pt_br)
        cls.home_pt.save_revision().publish()
        cls.pt_page = ContentPage(title="Sobre", slug="sobre-sitemap", locale=cls.pt_br)
        cls.home_pt.add_child(instance=cls.pt_page)

        cls.hidden = ContentPage(
            title="Hidden", slug="hidden-sitemap", locale=cls.pt_br, hide_from_search=True
        )
        cls.home_pt.add_child(instance=cls.hidden)

    def _paths(self):
        """Sitemap <loc>s as paths. They carry the Site's hostname, not
        `testserver`, so strip whatever host is there rather than a literal."""
        response = Client().get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        locs = re.findall(r"<loc>([^<]+)</loc>", response.content.decode())
        return [urlparse(loc).path for loc in locs]

    def test_a_country_trees_pages_are_listed(self):
        paths = self._paths()
        self.assertIn("/brasil/sobre-sitemap/", paths)

    def test_the_default_tree_is_still_listed(self):
        paths = self._paths()
        self.assertIn("/about-sitemap/", paths)
        self.assertIn("/", paths)

    def test_every_language_home_is_listed(self):
        paths = self._paths()
        self.assertIn("/brasil/", paths)

    def test_hide_from_search_is_still_honoured_in_a_country_tree(self):
        paths = self._paths()
        self.assertNotIn("/brasil/hidden-sitemap/", paths)

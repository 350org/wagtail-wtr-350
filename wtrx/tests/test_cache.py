"""
Tests for wtrx.cache — provider-agnostic CDN cache invalidation.

Covers:
- purge_all() is a silent no-op when WAGTAILFRONTENDCACHE is not configured
- purge_all() calls Cloudflare API with correct payload when CF backend is configured
- purge_all() falls back to URL-batch purge for unknown backends
- Registry dispatch routes to the correct handler
- _purge_all_cloudflare handles missing ZONEID gracefully
- _purge_all_cloudflare handles missing credentials gracefully
- _purge_all_cloudflare handles HTTP error responses gracefully
- _purge_all_cloudflare handles network exceptions gracefully
- on_settings_saved fires purge_all exactly once per explicit save for each of the 5 settings models
- on_page_published / on_page_unpublished fire purge_page_with_related
- on_page_slug_changed purges both the new URL and the old URL (via instance_before)
- purge_page_with_related is a silent no-op when WAGTAILFRONTENDCACHE is not configured
- purge_page_with_related purges parent IndexPage when parent is an IndexPage
- purge_page_with_related does not error when parent is not an IndexPage
- purge_page_with_related accepts extra_urls for additional URLs (e.g. old slug)
"""

import requests
from unittest.mock import MagicMock, call, patch

from django.test import TestCase, override_settings
from wagtail.models import Page, Site


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CF_BACKEND = "wagtail.contrib.frontend_cache.backends.CloudflareBackend"

_CF_SETTINGS = {
    "cloudflare": {
        "BACKEND": _CF_BACKEND,
        "BEARER_TOKEN": "test-token",
        "ZONEID": "test-zone",
    }
}

_UNKNOWN_BACKEND_SETTINGS = {
    "myprovider": {
        "BACKEND": "myapp.cache.MyCustomBackend",
    }
}


# ---------------------------------------------------------------------------
# purge_all() — no-op without configuration
# ---------------------------------------------------------------------------


class TestPurgeAllNoOp(TestCase):
    """purge_all() must be silent when WAGTAILFRONTENDCACHE is not set."""

    @override_settings(WAGTAILFRONTENDCACHE=None)
    @patch("wtrx.cache.requests.post")
    def test_does_not_call_requests_when_not_configured(self, mock_post):
        from wtrx.cache import purge_all

        purge_all()
        mock_post.assert_not_called()

    @override_settings()
    @patch("wtrx.cache.requests.post")
    def test_does_not_call_requests_when_setting_absent(self, mock_post):
        from django.conf import settings as django_settings

        # Ensure the setting is truly absent
        if hasattr(django_settings, "WAGTAILFRONTENDCACHE"):
            del django_settings.WAGTAILFRONTENDCACHE

        from wtrx.cache import purge_all

        purge_all()
        mock_post.assert_not_called()

    @override_settings(WAGTAILFRONTENDCACHE={})
    @patch("wtrx.cache.requests.post")
    def test_does_not_call_requests_when_empty_dict(self, mock_post):
        from wtrx.cache import purge_all

        purge_all()
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# purge_all() — Cloudflare backend
# ---------------------------------------------------------------------------


class TestPurgeAllCloudflare(TestCase):
    """purge_all() with a Cloudflare backend calls the CF API correctly."""

    @override_settings(WAGTAILFRONTENDCACHE=_CF_SETTINGS)
    @patch("wtrx.cache.requests.post")
    def test_calls_cf_purge_everything_endpoint(self, mock_post):
        from wtrx.cache import purge_all

        mock_post.return_value = MagicMock(ok=True)
        purge_all()

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("test-zone", args[0])
        self.assertEqual(kwargs["json"], {"purge_everything": True})

    @override_settings(WAGTAILFRONTENDCACHE=_CF_SETTINGS)
    @patch("wtrx.cache.requests.post")
    def test_uses_bearer_token_auth_header(self, mock_post):
        from wtrx.cache import purge_all

        mock_post.return_value = MagicMock(ok=True)
        purge_all()

        _, kwargs = mock_post.call_args
        self.assertIn("Authorization", kwargs["headers"])
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-token")

    @override_settings(
        WAGTAILFRONTENDCACHE={
            "cloudflare": {
                "BACKEND": _CF_BACKEND,
                "EMAIL": "user@example.com",
                "API_KEY": "legacy-key",
                "ZONEID": "test-zone",
            }
        }
    )
    @patch("wtrx.cache.requests.post")
    def test_uses_legacy_email_api_key_auth(self, mock_post):
        from wtrx.cache import purge_all

        mock_post.return_value = MagicMock(ok=True)
        purge_all()

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["X-Auth-Email"], "user@example.com")
        self.assertEqual(kwargs["headers"]["X-Auth-Key"], "legacy-key")

    @override_settings(
        WAGTAILFRONTENDCACHE={
            "cloudflare": {
                "BACKEND": _CF_BACKEND,
                "ZONEID": "test-zone",
                # No BEARER_TOKEN, no EMAIL/API_KEY
            }
        }
    )
    @patch("wtrx.cache.requests.post")
    def test_skips_when_no_credentials(self, mock_post):
        from wtrx.cache import purge_all

        purge_all()
        mock_post.assert_not_called()

    @override_settings(
        WAGTAILFRONTENDCACHE={
            "cloudflare": {
                "BACKEND": _CF_BACKEND,
                "BEARER_TOKEN": "test-token",
                # No ZONEID
            }
        }
    )
    @patch("wtrx.cache.requests.post")
    def test_skips_when_no_zone_id(self, mock_post):
        from wtrx.cache import purge_all

        purge_all()
        mock_post.assert_not_called()

    @override_settings(WAGTAILFRONTENDCACHE=_CF_SETTINGS)
    @patch("wtrx.cache.requests.post")
    def test_does_not_raise_on_http_error_response(self, mock_post):
        from wtrx.cache import purge_all

        mock_post.return_value = MagicMock(ok=False, status_code=403, text="Forbidden")
        # Should log an error but not raise
        purge_all()

    @override_settings(WAGTAILFRONTENDCACHE=_CF_SETTINGS)
    @patch(
        "wtrx.cache.requests.post",
        side_effect=requests.RequestException("network error"),
    )
    def test_does_not_raise_on_network_exception(self, mock_post):
        from wtrx.cache import purge_all

        # Should log an error but not propagate the exception
        purge_all()


# ---------------------------------------------------------------------------
# purge_all() — fallback handler for unknown backends
# ---------------------------------------------------------------------------


class TestPurgeAllFallback(TestCase):
    """purge_all() falls back to URL-batch purge for unknown backends."""

    @override_settings(WAGTAILFRONTENDCACHE=_UNKNOWN_BACKEND_SETTINGS)
    @patch("wtrx.cache._purge_all_fallback")
    def test_unknown_backend_dispatches_to_fallback(self, mock_fallback):
        from wtrx.cache import purge_all

        purge_all()
        mock_fallback.assert_called_once_with(
            "myprovider", _UNKNOWN_BACKEND_SETTINGS["myprovider"]
        )

    @override_settings(WAGTAILFRONTENDCACHE=_CF_SETTINGS)
    def test_cloudflare_backend_dispatches_to_cloudflare_handler(self):
        from wtrx.cache import PURGE_ALL_HANDLERS, purge_all

        mock_cf = MagicMock()
        with patch.dict(PURGE_ALL_HANDLERS, {_CF_BACKEND: mock_cf}):
            purge_all()
        mock_cf.assert_called_once_with("cloudflare", _CF_SETTINGS["cloudflare"])


# ---------------------------------------------------------------------------
# on_settings_saved signal — fires purge_all for each settings model
# ---------------------------------------------------------------------------


class TestOnSettingsSaved(TestCase):
    """on_settings_saved fires purge_all whenever any settings model is saved."""

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.get(is_default_site=True)

    @patch("wtrx.signals.purge_all")
    def test_branding_seo_settings_save_triggers_purge_all(self, mock_purge_all):
        from wtrx.site_settings import BrandingSEOSettings

        obj, _ = BrandingSEOSettings.objects.get_or_create(site=self.site)
        mock_purge_all.reset_mock()
        obj.save()
        mock_purge_all.assert_called_once()

    @patch("wtrx.signals.purge_all")
    def test_navigation_settings_save_triggers_purge_all(self, mock_purge_all):
        from wtrx.site_settings import NavigationSettings

        obj, _ = NavigationSettings.objects.get_or_create(site=self.site)
        mock_purge_all.reset_mock()
        obj.save()
        mock_purge_all.assert_called_once()

    @patch("wtrx.signals.purge_all")
    def test_footer_settings_save_triggers_purge_all(self, mock_purge_all):
        from wtrx.site_settings import FooterSettings

        obj, _ = FooterSettings.objects.get_or_create(site=self.site)
        mock_purge_all.reset_mock()
        obj.save()
        mock_purge_all.assert_called_once()

    @patch("wtrx.signals.purge_all")
    def test_social_settings_save_triggers_purge_all(self, mock_purge_all):
        from wtrx.site_settings import SocialSettings

        obj, _ = SocialSettings.objects.get_or_create(site=self.site)
        mock_purge_all.reset_mock()
        obj.save()
        mock_purge_all.assert_called_once()

    @patch("wtrx.signals.purge_all")
    def test_integration_settings_save_triggers_purge_all(self, mock_purge_all):
        from wtrx.site_settings import IntegrationSettings

        obj, _ = IntegrationSettings.objects.get_or_create(site=self.site)
        mock_purge_all.reset_mock()
        obj.save()
        mock_purge_all.assert_called_once()


# ---------------------------------------------------------------------------
# on_page_published / on_page_unpublished / on_page_slug_changed signals
# ---------------------------------------------------------------------------


class TestPageSignalHandlers(TestCase):
    """Signal handlers for page lifecycle events fire purge_page_with_related."""

    @patch("wtrx.signals.purge_page_with_related")
    def test_on_page_published_calls_purge_page_with_related(self, mock_purge):
        from wtrx.signals import on_page_published

        fake_page = MagicMock()
        on_page_published(sender=Page, instance=fake_page)
        mock_purge.assert_called_once_with(fake_page)

    @patch("wtrx.signals.purge_page_with_related")
    def test_on_page_unpublished_calls_purge_page_with_related(self, mock_purge):
        from wtrx.signals import on_page_unpublished

        fake_page = MagicMock()
        on_page_unpublished(sender=Page, instance=fake_page)
        mock_purge.assert_called_once_with(fake_page)

    @patch("wtrx.signals.purge_page_with_related")
    def test_on_page_slug_changed_purges_new_url(self, mock_purge):
        """Slug change with no instance_before calls purge_page_with_related once."""
        from wtrx.signals import on_page_slug_changed

        fake_page = MagicMock()
        on_page_slug_changed(sender=Page, instance=fake_page, instance_before=None)
        mock_purge.assert_called_once_with(fake_page, extra_urls=None)

    @patch("wtrx.signals.purge_page_with_related")
    def test_on_page_slug_changed_includes_old_url(self, mock_purge):
        """Slug change with instance_before passes the old URL as extra_urls."""
        from wtrx.signals import on_page_slug_changed

        fake_page = MagicMock()
        fake_old_page = MagicMock()
        fake_old_page.get_full_url.return_value = "http://example.com/old-slug/"

        on_page_slug_changed(
            sender=Page, instance=fake_page, instance_before=fake_old_page
        )
        mock_purge.assert_called_once_with(
            fake_page, extra_urls=["http://example.com/old-slug/"]
        )


# ---------------------------------------------------------------------------
# purge_page_with_related()
# ---------------------------------------------------------------------------


class TestPurgePageWithRelated(TestCase):
    """purge_page_with_related() purges page + parent IndexPage when applicable."""

    @classmethod
    def setUpTestData(cls):
        root = Page.objects.filter(depth=1).first()
        from wtrx.models import ContentPage, HomePage, IndexPage

        cls.home = HomePage(title="Home", slug="home-pwr-test")
        root.add_child(instance=cls.home)

        cls.index = IndexPage(title="Blog", slug="blog-pwr-test")
        cls.home.add_child(instance=cls.index)

        cls.child = ContentPage(title="Post", slug="post-pwr-test")
        cls.index.add_child(instance=cls.child)

        cls.standalone = ContentPage(title="Standalone", slug="standalone-pwr-test")
        cls.home.add_child(instance=cls.standalone)

    @override_settings(WAGTAILFRONTENDCACHE=None)
    @patch("wtrx.cache.PurgeBatch")
    def test_no_op_when_not_configured(self, mock_batch_cls):
        from wtrx.cache import purge_page_with_related

        purge_page_with_related(self.child)
        mock_batch_cls.assert_not_called()

    @override_settings(WAGTAILFRONTENDCACHE=_CF_SETTINGS)
    @patch("wtrx.cache.PurgeBatch")
    def test_purges_parent_index_page_when_parent_is_index(self, mock_batch_cls):
        from wtrx.cache import purge_page_with_related
        from wtrx.models import IndexPage

        mock_batch = MagicMock()
        mock_batch.urls = {"http://example.com/blog/post/", "http://example.com/blog/"}
        mock_batch_cls.return_value = mock_batch

        mock_parent = MagicMock(spec=IndexPage)
        mock_parent.get_full_url.return_value = "http://example.com/blog/"

        mock_page = MagicMock()
        mock_page.get_full_url.return_value = "http://example.com/blog/post/"
        mock_page.get_parent.return_value.specific = mock_parent

        purge_page_with_related(mock_page)

        # add_url was called twice: child + parent
        self.assertEqual(mock_batch.add_url.call_count, 2)
        mock_batch.purge.assert_called_once()

    @override_settings(WAGTAILFRONTENDCACHE=_CF_SETTINGS)
    @patch("wtrx.cache.PurgeBatch")
    def test_does_not_add_parent_when_parent_is_not_index_mock(self, mock_batch_cls):
        from wtrx.cache import purge_page_with_related
        from wtrx.models import ContentPage

        mock_batch = MagicMock()
        mock_batch.urls = {"http://example.com/standalone/"}
        mock_batch_cls.return_value = mock_batch

        mock_parent = MagicMock(spec=ContentPage)
        mock_parent.get_full_url.return_value = "http://example.com/"

        mock_page = MagicMock()
        mock_page.get_full_url.return_value = "http://example.com/standalone/"
        mock_page.get_parent.return_value.specific = mock_parent

        purge_page_with_related(mock_page)

        # add_url should only be called once (the page itself, not the ContentPage parent)
        mock_batch.add_url.assert_called_once_with("http://example.com/standalone/")
        mock_batch.purge.assert_called_once()

    @override_settings(WAGTAILFRONTENDCACHE=_CF_SETTINGS)
    @patch("wtrx.cache.PurgeBatch")
    def test_does_not_raise_when_page_has_no_parent(self, mock_batch_cls):
        """A page without a parent (e.g. Wagtail root) should not cause an error."""
        from wtrx.cache import purge_page_with_related

        mock_batch = MagicMock()
        mock_batch.urls = set()
        mock_batch_cls.return_value = mock_batch

        # Pass a mock page with no parent
        fake_page = MagicMock()
        fake_page.get_full_url.return_value = None
        fake_page.get_parent.side_effect = Exception("no parent")

        # Should not raise
        purge_page_with_related(fake_page)

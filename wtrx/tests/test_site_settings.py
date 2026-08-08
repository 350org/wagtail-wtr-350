"""
Tests for DonateBlock's resolution of the ActBlue integration config.

donation_suggested_amounts parsing used to be a property on
IntegrationSettings; it now lives in DonateBlock.get_context() (see
wtrx/blocks/__init__.py), reading the enabled "actblue" integration entry
from IntegrationSettings.integrations.
"""

from django.test import RequestFactory, TestCase
from wagtail.models import Site

from wtrx.blocks import DonateBlock
from wtrx.site_settings import IntegrationSettings


class TestDonateBlockSuggestedAmounts(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.get(is_default_site=True)
        cls.integration, _ = IntegrationSettings.objects.get_or_create(
            site=cls.site,
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.block = DonateBlock()

    def _set_amounts(self, value):
        self.integration.integrations = [
            (
                "actblue",
                {
                    "enabled": True,
                    "base_url": "",
                    "suggested_amounts": value,
                    "default_recurring": False,
                },
            )
        ]
        self.integration.save()

    def _amounts_list(self):
        value = self.block.to_python({})
        request = self.factory.get("/")
        ctx = self.block.get_context(value, parent_context={"request": request})
        return ctx["donation_suggested_amounts_list"]

    def test_parses_comma_separated_integers(self):
        self._set_amounts("10,25,50,100")
        self.assertEqual(self._amounts_list(), [10, 25, 50, 100])

    def test_handles_whitespace(self):
        self._set_amounts(" 10 , 25 , 50 ")
        self.assertEqual(self._amounts_list(), [10, 25, 50])

    def test_empty_string_returns_empty_list(self):
        self._set_amounts("")
        self.assertEqual(self._amounts_list(), [])

    def test_blank_returns_empty_list(self):
        self._set_amounts("   ")
        self.assertEqual(self._amounts_list(), [])

    def test_invalid_values_return_empty_list(self):
        self._set_amounts("abc,def")
        self.assertEqual(self._amounts_list(), [])

    def test_single_value(self):
        self._set_amounts("50")
        self.assertEqual(self._amounts_list(), [50])

    def test_trailing_comma_ignored(self):
        self._set_amounts("10,25,")
        self.assertEqual(self._amounts_list(), [10, 25])

    def test_no_actblue_config_returns_empty_list(self):
        self.integration.integrations = []
        self.integration.save()
        self.assertEqual(self._amounts_list(), [])

    def test_no_request_returns_empty_list(self):
        self._set_amounts("10,25")
        value = self.block.to_python({})
        ctx = self.block.get_context(value, parent_context=None)
        self.assertEqual(ctx["donation_suggested_amounts_list"], [])

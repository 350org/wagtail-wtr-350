"""
Tests for IntegrationSettings helper methods and properties.
"""

from django.test import TestCase
from wagtail.models import Site

from wtrx.site_settings import IntegrationSettings


class TestDonationSuggestedAmountsList(TestCase):
    """IntegrationSettings.donation_suggested_amounts_list property."""

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.get(is_default_site=True)
        cls.integration, _ = IntegrationSettings.objects.get_or_create(
            site=cls.site,
        )

    def _set_amounts(self, value):
        self.integration.donation_suggested_amounts = value
        self.integration.save()

    def test_parses_comma_separated_integers(self):
        self._set_amounts("10,25,50,100")
        self.assertEqual(
            self.integration.donation_suggested_amounts_list,
            [10, 25, 50, 100],
        )

    def test_handles_whitespace(self):
        self._set_amounts(" 10 , 25 , 50 ")
        self.assertEqual(
            self.integration.donation_suggested_amounts_list,
            [10, 25, 50],
        )

    def test_empty_string_returns_empty_list(self):
        self._set_amounts("")
        self.assertEqual(self.integration.donation_suggested_amounts_list, [])

    def test_blank_returns_empty_list(self):
        self._set_amounts("   ")
        self.assertEqual(self.integration.donation_suggested_amounts_list, [])

    def test_invalid_values_return_empty_list(self):
        self._set_amounts("abc,def")
        self.assertEqual(self.integration.donation_suggested_amounts_list, [])

    def test_single_value(self):
        self._set_amounts("50")
        self.assertEqual(
            self.integration.donation_suggested_amounts_list,
            [50],
        )

    def test_trailing_comma_ignored(self):
        self._set_amounts("10,25,")
        self.assertEqual(
            self.integration.donation_suggested_amounts_list,
            [10, 25],
        )

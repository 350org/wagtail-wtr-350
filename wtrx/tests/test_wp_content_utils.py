"""
Tests for wtrx.management.commands._wp_content_utils's Cloudflare
email-obfuscation handling (_decode_cf_email / _unmask_cf_emails).

Cloudflare's "Email Address Obfuscation" marks the obfuscated text with
class="__cf_email__" data-cfemail="<hex>", but which element carries that
mark depends on the original markup: a separate <span> nested inside the
<a> when the email text wasn't already the anchor's sole content, or
directly on the <a> itself (no span) when it was. A real 350.org press
release uses the latter shape and was left completely unfixed by an
earlier version of _unmask_cf_emails that only looked for a <span>.
"""

from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from wtrx.management.commands._wp_content_utils import _decode_cf_email, _unmask_cf_emails


def _cf_encode(email, key=0x2B):
    return format(key, "02x") + "".join(format(ord(c) ^ key, "02x") for c in email)


class TestDecodeCfEmail(SimpleTestCase):
    def test_round_trips(self):
        encoded = _cf_encode("media@350.org")
        self.assertEqual(_decode_cf_email(encoded), "media@350.org")

    def test_matches_real_world_hex(self):
        # Captured from a live 350.org press release page.
        self.assertEqual(
            _decode_cf_email("1c75707d727b326d6975767d72735c2f292c32736e7b"),
            "ilang.quijano@350.org",
        )


class TestUnmaskCfEmails(SimpleTestCase):
    def test_nested_span_shape(self):
        """class/data-cfemail on a <span> nested inside the <a>."""
        encoded = _cf_encode("media@350.org")
        html = (
            f'<p>Contact <a href="/cdn-cgi/l/email-protection#{encoded}">'
            f'<span class="__cf_email__" data-cfemail="{encoded}">[email&#160;protected]</span>'
            f"</a></p>"
        )
        soup = BeautifulSoup(html, "html.parser")
        _unmask_cf_emails(soup)
        anchor = soup.find("a")
        self.assertEqual(anchor["href"], "mailto:media@350.org")
        self.assertEqual(anchor.get_text(), "media@350.org")
        self.assertIsNone(soup.find("span"))

    def test_attributes_directly_on_anchor_shape(self):
        """class/data-cfemail on the <a> itself, no nested <span> at all —
        the shape that silently defeated the span-only lookup."""
        encoded = "1c75707d727b326d6975767d72735c2f292c32736e7b"
        html = (
            f'<p>Media Campaigner, <a href="/cdn-cgi/l/email-protection" '
            f'class="__cf_email__" data-cfemail="{encoded}">[email&#160;protected]</a>, '
            f"+639175810934</p>"
        )
        soup = BeautifulSoup(html, "html.parser")
        _unmask_cf_emails(soup)
        anchor = soup.find("a")
        self.assertEqual(anchor["href"], "mailto:ilang.quijano@350.org")
        self.assertEqual(anchor.get_text(), "ilang.quijano@350.org")

    def test_missing_data_cfemail_is_left_alone(self):
        html = '<p><span class="__cf_email__">[email&#160;protected]</span></p>'
        soup = BeautifulSoup(html, "html.parser")
        _unmask_cf_emails(soup)
        self.assertIsNotNone(soup.find("span", class_="__cf_email__"))

    def test_invalid_hex_is_left_alone(self):
        html = '<p><span class="__cf_email__" data-cfemail="zz">[email&#160;protected]</span></p>'
        soup = BeautifulSoup(html, "html.parser")
        _unmask_cf_emails(soup)
        self.assertIsNotNone(soup.find("span", class_="__cf_email__"))

    def test_no_email_markup_is_a_no_op(self):
        html = "<p>Nothing to see here.</p>"
        soup = BeautifulSoup(html, "html.parser")
        _unmask_cf_emails(soup)
        self.assertEqual(str(soup), html)

"""Tests for the import_350_how_to_give_modals converter."""

from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from wtrx.blocks import CardModalContentBlock
from wtrx.management.commands.import_350_how_to_give_modals import _iter_cards, convert_modal


def _div(html):
    return BeautifulSoup(f'<div id="m">{html}</div>', "html.parser").div


class TestConvertModal(SimpleTestCase):
    def test_plain_copy_becomes_one_text_child(self):
        children = convert_modal(_div("<p>One.</p><ul><li>Two</li></ul>"))
        self.assertEqual([c["type"] for c in children], ["text"])
        self.assertEqual(children[0]["value"], "<p>One.</p><ul><li>Two</li></ul>")

    def test_bare_inline_content_in_a_div_is_wrapped_in_a_paragraph(self):
        children = convert_modal(_div('<div class="padding-left-medium">350.org<br/>PO Box 1<br/><br/></div>'))
        self.assertEqual(children[0]["value"], "<p>350.org<br/>PO Box 1</p>")

    def test_scripts_become_raw_html_in_place(self):
        children = convert_modal(_div(
            "<p>Before.</p>"
            '<script>_settings="x"</script><script src="https://www.dafdirect.org/w.js"></script>'
            "<p>After.</p>"
        ))
        self.assertEqual([c["type"] for c in children], ["text", "raw_html", "text"])
        self.assertIn("dafdirect.org/w.js", children[1]["value"])
        self.assertIn('_settings="x"', children[1]["value"])

    def test_cloudflare_scripts_are_dropped(self):
        children = convert_modal(_div(
            '<p>Hi.</p><script src="/cdn-cgi/scripts/x/email-decode.min.js"></script>'
        ))
        self.assertEqual([c["type"] for c in children], ["text"])

    def test_text_strong_paragraph_keeps_its_bold(self):
        children = convert_modal(_div('<p class="text-strong">IRA gifts.</p>'))
        self.assertEqual(children[0]["value"], "<p><strong>IRA gifts.</strong></p>")

    def test_fundraiseup_form_link_is_made_relative(self):
        children = convert_modal(_div(
            '<p><a href="https://350.org/how-to-give/?r=US&amp;form=FUNABC">Join</a></p>'
        ))
        self.assertIn('href="?form=FUNABC"', children[0]["value"])

    def test_output_validates_as_modal_content(self):
        block = CardModalContentBlock()
        children = convert_modal(_div("<h3>Title</h3><p>Body.</p><script>x=1</script>"))
        block.clean(block.to_python(children))


class TestIterCards(SimpleTestCase):
    def test_finds_cards_nested_in_list_and_section_blocks(self):
        body = [
            {"type": "section", "value": {"content": [
                {"type": "card_grid", "value": {"cards": [
                    {"type": "item", "value": {"content": "<h3>A</h3>", "link_url": "https://350.org/#a"}},
                ]}},
            ]}},
        ]
        self.assertEqual([c["link_url"] for c in _iter_cards(body)], ["https://350.org/#a"])

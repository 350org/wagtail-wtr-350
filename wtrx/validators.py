"""
Shared, dependency-free validators.

Deliberately its own leaf module rather than living in wtrx/blocks/__init__.py
(where the tag-balance checker originated, for RawHTMLBlock -- see AGENTS.md
pitfall #43) or wtrx/site_settings.py: blocks/__init__.py already imports
IntegrationSettings from site_settings.py, so anything site_settings.py needs
from blocks/__init__.py (as IntegrationSettings.custom_head_html/
custom_body_html do, for the same tag-balance check RawHTMLBlock uses) would
be a circular import if it stayed there. This module imports from neither, so
both can import from it safely.
"""

from html.parser import HTMLParser

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

_VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class TagBalanceParser(HTMLParser):
    """
    Tracks open-tag nesting to catch the most common pasted-embed mistake
    (a stray or missing closing tag). Does not validate full HTML5
    conformance (attribute syntax etc.) — that would be noisy against
    legitimate third-party embed codes, which is exactly what this exists
    to tolerate. HTMLParser doesn't descend into <script>/<style> content
    as tags, so inline JS/CSS containing "<"/">" is not an issue.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.mismatched = False

    def handle_starttag(self, tag, attrs):
        if tag not in _VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in _VOID_ELEMENTS:
            return
        if not self.stack or self.stack[-1] != tag:
            self.mismatched = True
        elif self.stack:
            self.stack.pop()

    @property
    def is_balanced(self):
        return not self.mismatched and not self.stack


def html_is_balanced(value):
    parser = TagBalanceParser()
    parser.feed(value)
    parser.close()
    return parser.is_balanced


def validate_balanced_html(value):
    """
    Django model-field validator wrapping html_is_balanced() — the same
    check RawHTMLBlock.clean() (wtrx/blocks/__init__.py) runs for
    StreamField content, applied here to plain model TextFields (e.g.
    IntegrationSettings.custom_head_html/custom_body_html) that also hold
    pasted third-party markup.
    """
    if value and not html_is_balanced(value):
        raise ValidationError(
            _(
                "This HTML appears to have mismatched or unclosed tags — "
                "check that every opening tag has a matching closing tag."
            )
        )

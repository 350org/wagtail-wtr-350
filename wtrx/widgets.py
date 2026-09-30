"""
Admin form widgets.
"""

from django.forms import Media
from django.utils.functional import cached_property

from wagtail.admin.rich_text import DraftailRichTextArea
from wagtail.admin.staticfiles import versioned_static


class HeadlineRichTextArea(DraftailRichTextArea):
    """
    Draftail for the hero headline, whose feature list is empty (no "ai").

    Every Wagtail webpack entry has its own runtime, so each one that loads
    React overwrites `window.React` with its own copy, and wagtail-ai's
    draftail.js reads that global once, when it loads. On a form whose
    first Draftail has no "ai" feature, Django's media merge put
    telepath/blocks.js between Wagtail's draftail.js and wagtail-ai's, so
    wagtail-ai grabbed blocks.js's React and every AI-enabled editor in the
    body crashed with React error #321. Listing wagtail-ai's script here
    keeps it directly after draftail.js. Loading it registers the plugin
    only; the toolbar button still appears only on fields with "ai".
    """

    @cached_property
    def media(self):
        return super().media + Media(js=[versioned_static("wagtail_ai/draftail.js")])

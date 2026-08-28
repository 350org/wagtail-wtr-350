"""
Shared constants for the wtrx app.

These are importable from any app without pulling in the full blocks module,
which avoids circular import issues and keeps the dependency graph clean.
"""

# ---------------------------------------------------------------------------
# Field length constants
# ---------------------------------------------------------------------------

CHARFIELD_MAX_LENGTH = 255

# ---------------------------------------------------------------------------
# Rich text feature sets
#
# RICHTEXT_FEATURES_FULL:   headings, inline formatting, links, lists, blockquote.
#                           Used for body-level rich text (TextBlock, QuoteBlock, etc.).
#
# RICHTEXT_FEATURES_INLINE: bold, italic, link only.
#                           Used for short rich text (descriptions, intro fields).
#
# RICHTEXT_FEATURES_HERO:   inline formatting + lists (no headings, no blockquote).
#                           Used for HeroMixin.hero_copy where lists are useful
#                           but headings would conflict with the hero headline.
#
# RICHTEXT_FEATURES_HEADING_H2: inline formatting + h2 only. Used by blocks whose
#                           separate heading + text fields were condensed into one
#                           richtext field — the editor types the heading as an H2
#                           at the top (ImageTextBlock, FeaturePanelBlock,
#                           CardCarouselBlock).
#
# RICHTEXT_FEATURES_HEADINGS_H2_H3: the same, plus h3 — for a block that also had
#                           a separate subheading field (CalloutBlock).
#
# "ai" is included in all of these: it's a Draftail toolbar control (wagtail-ai)
# that doesn't add any markup/content-state of its own, so it's safe to offer
# everywhere rich text is edited. wagtail-ai only adds it to fields whose
# `features` list is explicit — like all of these — if it's listed here.
# ---------------------------------------------------------------------------

RICHTEXT_FEATURES_FULL = [
    "h2",
    "h3",
    "h4",
    "bold",
    "italic",
    "link",
    "ol",
    "ul",
    "blockquote",
    "ai",
]

RICHTEXT_FEATURES_INLINE = ["bold", "italic", "link", "ai"]

RICHTEXT_FEATURES_HERO = ["bold", "italic", "link", "ol", "ul", "ai"]

RICHTEXT_FEATURES_HEADING_H2 = ["h2", "bold", "italic", "link", "ai"]

RICHTEXT_FEATURES_HEADINGS_H2_H3 = ["h2", "h3", "bold", "italic", "link", "ai"]

# RICHTEXT_FEATURES_HEADING_H3: inline formatting + h3 only. For a card-shaped
# block whose heading rendered as an H3, not an H2 (CardBlock, ImageCardListItemBlock).
RICHTEXT_FEATURES_HEADING_H3 = ["h3", "bold", "italic", "link", "ai"]

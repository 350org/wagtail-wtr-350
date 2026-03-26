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
#                           Used for body-level rich text (TextBlock, CalloutBlock, etc.).
#
# RICHTEXT_FEATURES_INLINE: bold, italic, link only.
#                           Used for short rich text (descriptions, intro fields).
#
# RICHTEXT_FEATURES_HERO:   inline formatting + lists (no headings, no blockquote).
#                           Used for HeroMixin.hero_copy where lists are useful
#                           but headings would conflict with the hero headline.
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
]

RICHTEXT_FEATURES_INLINE = ["bold", "italic", "link"]

RICHTEXT_FEATURES_HERO = ["bold", "italic", "link", "ol", "ul"]

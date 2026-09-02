"""
create_test_page management command.

Creates a ContentPage under the site root that exercises **every** block type
registered in BodyStreamBlock, in every meaningful configuration, plus a
typography reference showing the full heading ramp (h1-h6) and body copy.
Load the page to verify everything renders without errors and at the right
size.

Only runs when DEBUG=True.

Usage:
    python manage.py create_test_page
    python manage.py create_test_page --slug my-test-page
    python manage.py create_test_page --force  # overwrite if page already exists

The command is safe to run repeatedly with --force. Without --force it skips
creation if a page with the given slug already exists.

Some blocks need a real page to point at (PageCardsBlock needs an index page,
SignupWagtailFormsBlock needs a FormPage). Rather than depending on whatever
happens to be in the database, this command builds those as children of the
test page itself, so the fixture is self-contained and `--force` cleans the
whole thing up in one delete.

Keeping this in sync
--------------------
When a block is added to (or a field added to) ``BodyStreamBlock`` /
``SectionContentBlock`` in ``wtrx/blocks/__init__.py``, add a matching builder
here and reference it from ``_build_body()``. ``wtrx/tests/test_create_test_page.py``
asserts that every block name registered in ``BodyStreamBlock`` appears in the
generated page, so a forgotten block fails the test suite rather than quietly
going untested.
"""

import json
import os
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


# ---------------------------------------------------------------------------
# Sample content
# ---------------------------------------------------------------------------

_RICHTEXT_PARAGRAPH = (
    "<p>This is a sample paragraph of rich text. It contains <b>bold</b>, "
    "<i>italic</i>, and a <a href=\"https://example.com\">link</a>.</p>"
)

_RICHTEXT_INLINE = (
    "<p>Short supporting copy with <b>bold</b> and a "
    "<a href=\"https://example.com\">link</a>.</p>"
)

# A rich text value using every feature RICHTEXT_FEATURES_FULL offers:
# h2, h3, h4, bold, italic, link, ol, ul, blockquote. h1/h5/h6 are not
# reachable from the editor at all — they are demonstrated separately in the
# raw-HTML heading ramp below.
_RICHTEXT_KITCHEN_SINK = (
    "<h2>Rich text heading 2</h2>"
    "<p>Body copy sits at 20px from the <code>sm:</code> breakpoint up "
    "(<code>text-lg sm:text-xl</code>). Every heading step outside the hero is "
    "sized against that. This paragraph is long enough to wrap on a desktop "
    "viewport so line height and measure can be judged alongside the headings "
    "above and below it.</p>"
    "<h3>Rich text heading 3</h3>"
    "<p>A second paragraph, with <b>bold text</b>, <i>italic text</i>, and an "
    "<a href=\"https://example.com\">external link</a> to check the link colour "
    "and underline offset.</p>"
    "<h4>Rich text heading 4</h4>"
    "<p>h4 is the last heading level the editor offers. It is pinned to the "
    "body step so it never collapses into a bold paragraph.</p>"
    "<ul><li>Unordered list item one</li>"
    "<li>Unordered list item two, long enough to wrap onto a second line so "
    "the hanging indent can be checked</li>"
    "<li>Unordered list item three</li></ul>"
    "<ol><li>Ordered list item one</li>"
    "<li>Ordered list item two</li>"
    "<li>Ordered list item three</li></ol>"
    "<blockquote>A blockquote, for a pulled line of copy that is not big "
    "enough to warrant the full Quote block.</blockquote>"
)

# The heading ramp. Rendered as raw HTML inside the same wrapper text_block.html
# uses, so h2/h3/h4 pick up the real .wtr-text-block rules from main.css and
# h1/h5/h6 show what they actually fall back to (prose defaults — neither is
# reachable from the rich text editor, and neither is styled by .wtr-text-block).
_HEADING_RAMP_HTML = (
    '<div class="wtr-text-block prose prose-neutral max-w-none text-lg sm:text-xl">'
    "<h1>Heading 1 &mdash; page title</h1>"
    "<p>An h1 is never authored in a block: it is the page title, rendered by "
    "the hero at the top of this page. Shown here only for comparison.</p>"
    "<h2>Heading 2 &mdash; section heading</h2>"
    "<p>Body copy following an h2.</p>"
    "<h3>Heading 3 &mdash; sub-heading</h3>"
    "<p>Body copy following an h3.</p>"
    "<h4>Heading 4 &mdash; minor heading</h4>"
    "<p>Body copy following an h4. This is the last level the rich text editor "
    "offers.</p>"
    "<h5>Heading 5 &mdash; not editor-reachable</h5>"
    "<p>h5 has no rule in <code>.wtr-text-block</code> and falls back to the "
    "typography plugin&rsquo;s default.</p>"
    "<h6>Heading 6 &mdash; not editor-reachable</h6>"
    "<p>Same for h6.</p>"
    "<p><b>Bold body copy.</b> <i>Italic body copy.</i> "
    '<a href="https://example.com">A link in body copy.</a> '
    "<code>Inline code.</code></p>"
    "</div>"
)

# The size ramp, one row per step, labelled with the utility that produces it.
#
# Sizes are set with `style="font-size: var(--text-*)"` rather than the utility
# class itself on purpose: Tailwind's scanner would have to pick these class
# names out of a Python file for the utilities to be emitted, and a step that
# is currently used nowhere in a template would silently render at the
# inherited size instead of its real one. The CSS variables are emitted at
# :root unconditionally, so reading them directly is always accurate.
_TYPE_SCALE_ROWS = [
    ("text-8xl", "--text-8xl", "96px", "Hero display headline (image/video hero) and nothing else"),
    ("text-64", "--text-64", "64px", "Hero banner headline. Hero-only — see AGENTS.md #34"),
    ("text-5xl", "--text-5xl", "48px", "H2 display: CardGrid, CardCarousel, PageCards, ImageCardList"),
    ("text-40", "--text-40", "40px", "H2 section: Callout, ImageText, DonateFundraiseUp, rich text h2"),
    ("text-36", "--text-36", "36px", "Legacy step — kept as a token, no longer used outside the hero"),
    ("text-32", "--text-32", "32px", "Utility H1: 404, search results, no-CMS-access"),
    ("text-3xl", "--text-3xl", "30px", "Rich text h2 at the sm: breakpoint"),
    ("text-28", "--text-28", "28px", "H2 minor: signup/donate headings, rich text h3"),
    ("text-2xl", "--text-2xl", "24px", "Lead copy: PageCards, related posts"),
    ("text-xl", "--text-xl", "20px", "Body paragraph (sm: and up), rich text h4"),
    ("text-lg", "--text-lg", "18px", "Body paragraph below the sm: breakpoint"),
    ("text-base", "--text-base", "16px", "Tailwind default — deliberately not the body size here"),
    ("text-sm", "--text-sm", "14px", "Chrome: nav, footer, form labels, pagination, pills, captions"),
]

_SAMPLE_TABLE = {
    "data": [
        ["Region", "Coal plants retired", "Renewable capacity added"],
        ["Africa", "12", "4.1 GW"],
        ["Asia", "48", "31.7 GW"],
        ["Europe", "23", "18.2 GW"],
        ["Latin America", "9", "7.5 GW"],
    ],
    "first_row_is_table_header": True,
    "first_col_is_header": False,
    "table_caption": "Sample data table",
}

#: Every key in BACKGROUND_COLOR_CHOICES. Imported lazily in handle() and
#: cross-checked against this list so a new palette entry surfaces here
#: instead of silently going untested.
_BACKGROUND_KEYS = [
    "white",
    "light-grey",
    "dark-grey",
    "navy",
    "red",
    "blue-gradient",
]


# ---------------------------------------------------------------------------
# StreamField helpers
# ---------------------------------------------------------------------------


def _sb(block_type, value):
    """Build one StreamField entry with a stable UUID."""
    return {"type": block_type, "value": value, "id": str(uuid.uuid4())}


def _label(text, note=""):
    """
    A raw-HTML divider naming the block that follows.

    Styled with inline CSS rather than Tailwind utilities so it renders
    identically whether or not those class names happen to be in the compiled
    bundle — this is QA scaffolding, not site markup.
    """
    note_html = (
        f'<span style="text-transform:none;letter-spacing:0;opacity:.7">'
        f" &mdash; {note}</span>"
        if note
        else ""
    )
    return _sb(
        "raw_html",
        f'<div style="margin:4rem 0 1rem;padding-top:1rem;'
        f"border-top:2px dashed #9aa5a8;font:700 13px/1.4 ui-monospace,monospace;"
        f'letter-spacing:.08em;text-transform:uppercase;color:#4a5568">'
        f"{text}{note_html}</div>",
    )


def _heading(text):
    """A big section divider for the top-level groups of the test page."""
    return _sb(
        "raw_html",
        f'<div style="margin:6rem 0 1rem;padding:1rem 1.25rem;background:#0F81E9;'
        f'color:#fff;font:700 22px/1.2 system-ui,sans-serif;border-radius:6px">'
        f"{text}</div>",
    )


def _make_test_image(title="Placeholder Image"):
    """
    Create and return a CustomImage loaded from the committed fixture at
    fixtures/placeholder.png.

    Using a real image file ensures image-bearing blocks render visually
    during QA rather than falling back to their no-image branch.
    """
    from django.conf import settings as django_settings
    from django.core.files.uploadedfile import SimpleUploadedFile

    from wtrx.images import CustomImage

    fixture_path = os.path.join(django_settings.BASE_DIR, "fixtures", "placeholder.png")
    with open(fixture_path, "rb") as fh:
        png_bytes = fh.read()

    uploaded = SimpleUploadedFile("placeholder.png", png_bytes, content_type="image/png")
    image = CustomImage(title=title, file=uploaded)
    image.save()
    return image


# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------


def _type_scale_html():
    rows = []
    for utility, var, px, usage in _TYPE_SCALE_ROWS:
        rows.append(
            '<div style="display:flex;align-items:baseline;gap:1.5rem;'
            'padding:.75rem 0;border-bottom:1px solid #e2e8f0">'
            '<code style="flex:0 0 7.5rem;font:700 13px ui-monospace,monospace;'
            f'color:#0F81E9">{utility}</code>'
            '<code style="flex:0 0 4rem;font:400 13px ui-monospace,monospace;'
            f'color:#4a5568">{px}</code>'
            f'<div style="flex:1 1 auto;min-width:0;font-size:var({var});'
            'line-height:1.15;overflow:hidden;text-overflow:ellipsis;'
            'white-space:nowrap">The quick brown fox</div>'
            '<div style="flex:0 0 20rem;font:400 12px/1.4 system-ui,sans-serif;'
            f'color:#4a5568">{usage}</div>'
            "</div>"
        )
    return (
        '<div style="font-family:system-ui,sans-serif">'
        + "".join(rows)
        + "</div>"
    )


def _typography_blocks():
    """The typography reference: heading ramp, size ramp, rich text sample."""
    return [
        _heading("1. Typography"),
        _label("heading ramp", "h1-h6 plus body copy, in the real rich text container"),
        _sb("raw_html", _HEADING_RAMP_HTML),
        _label("type scale", "every --text-* step, largest first"),
        _sb("raw_html", _type_scale_html()),
        _label("text", "rich text block, every editor-available feature"),
        _sb("text", _RICHTEXT_KITCHEN_SINK),
    ]


# ---------------------------------------------------------------------------
# Block builders — one per block type in BodyStreamBlock
# ---------------------------------------------------------------------------


def _text_block():
    return _sb("text", _RICHTEXT_PARAGRAPH)


def _lead_text_block():
    return _sb(
        "lead_text",
        "<p>This is a lead paragraph — larger than ordinary body copy, "
        "for opening a page or section with one standout statement.</p>",
    )


def _image_block_full(image_id):
    """ImageBlock with caption and explicit alt text."""
    return _sb(
        "image",
        {
            "image": image_id,
            "alt_text": "A test image with explicit alt text",
            "caption": "Sample image caption",
        },
    )


def _image_block_minimal(image_id):
    """ImageBlock without optional fields — alt text falls back to the title."""
    return _sb("image", {"image": image_id, "alt_text": "", "caption": ""})


def _video_block():
    return _sb(
        "video",
        {
            "embed_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "media_file": None,
            "caption": "Sample video caption",
        },
    )


def _button_block(style, text, anchor=None):
    return _sb(
        "button",
        {
            "text": text,
            "link_page": None,
            "link_url": None if anchor else "https://example.com",
            "anchor": anchor or "",
            "style": style,
        },
    )


def _button_group_block(count=3, layout="horizontal"):
    labels = ["Take Action", "Learn More", "Donate", "Volunteer", "Share"]
    styles = ["primary", "outline", "secondary", "primary", "outline"]
    return _sb(
        "button_group",
        {
            "buttons": [
                {
                    "text": labels[i],
                    "link_page": None,
                    "link_url": "https://example.com",
                    "anchor": "",
                    "style": styles[i],
                }
                for i in range(count)
            ],
            "layout": layout,
        },
    )


def _raw_html_block():
    return _sb(
        "raw_html",
        '<div style="border:2px dashed #9aa5a8;border-radius:8px;padding:24px;'
        'font-family:ui-monospace,monospace">'
        '<p style="margin:0 0 12px;font-weight:700">Embedded HTML</p>'
        '<p style="margin:0">Rendered verbatim, exactly as pasted.</p></div>',
    )


def _table_block():
    return _sb("table", _SAMPLE_TABLE)


def _card_value(heading, description="", image_id=None, icon_id=None, tag="", link=True):
    """A CardBlock value — shared by the standalone card, the grid and the carousel."""
    content = f"<h3>{heading}</h3>"
    if description:
        content += f"<p>{description}</p>"
    return {
        "tag": tag,
        "icon": icon_id,
        "content": content,
        "image": image_id,
        "link_page": None,
        "link_url": "https://example.com" if link else None,
        "link_text": "Learn more" if link else "",
    }


def _card_block_full(image_id):
    """Standalone CardBlock — every field populated."""
    return _sb(
        "card",
        _card_value(
            "Standalone Card (all fields)",
            description="Tag pill, icon, image, description and a CTA link.",
            image_id=image_id,
            icon_id=image_id,
            tag="Global",
        ),
    )


def _card_block_minimal():
    """Standalone CardBlock — heading only."""
    return _sb(
        "card",
        _card_value("Standalone Card (minimal)", link=False),
    )


def _person_card_block_full(image_id):
    return _sb(
        "person_card",
        {
            "name": "Jane Sample",
            "role": "Campaign Manager",
            "image": image_id,
            "bio": "Jane has worked in grassroots organizing for over a decade.",
            "email": "jane@example.com",
            "phone": "555-867-5309",
            "website": "https://example.com",
        },
    )


def _person_card_block_minimal():
    return _sb(
        "person_card",
        {
            "name": "Bob Minimal",
            "role": "",
            "image": None,
            "bio": "",
            "email": "",
            "phone": "",
            "website": "",
        },
    )


def _person_card_grid_block(image_id, count, heading="Person Card Grid"):
    """
    PersonCardGridBlock with `count` people, to eyeball _person_grid_rows()'s
    row-balancing (e.g. count=5 -> 3+2, count=7 -> 3+2+2, no orphan row).
    """
    people = [
        {
            "name": f"Person {i + 1}",
            "role": "Organizer",
            "image": image_id,
            "bio": "",
            "email": "",
            "phone": "",
            "website": "",
        }
        for i in range(count)
    ]
    return _sb("person_card_grid", {"heading": heading, "people": people})


def _image_grid_block(image_id, count=5, heading="Image Grid"):
    images = [{"image": image_id, "alt_text": f"Grid image {i + 1}"} for i in range(count)]
    return _sb("image_grid", {"heading": heading, "images": images})


def _logo_grid_block(image_id, count=6, heading="Logo Grid"):
    logos = [
        {
            "image": image_id,
            "name": f"Partner Org {i + 1}",
            "link_page": None,
            "link_url": "https://example.com" if i % 2 == 0 else "",
        }
        for i in range(count)
    ]
    return _sb("logo_grid", {"heading": heading, "logos": logos})


def _card_grid_block(image_id, count=3, heading="Card Grid"):
    """
    CardGridBlock with a mix of cards.

    ``count`` exists to eyeball _balanced_rows()'s dynamic row-balancing
    (max_per_row=3, see card_grid_block.html/AGENTS.md pitfall #44) —
    count=4 gives 2x2, count=7 gives 3+2+2 (the old CSS-only special case
    left an unbalanced 3+3+1 at 7, the regression this now fixes).
    """
    base_cards = [
        _card_value(
            "With image and tag",
            description="Image, tag pill and an external link.",
            image_id=image_id,
            tag="Featured",
        ),
        _card_value(
            "No image",
            description="No image, but still linked.",
        ),
        _card_value(
            "Description only",
            description="No image and no link.",
            link=False,
        ),
        _card_value(
            "With icon",
            description="An icon beside the heading rather than a banner image.",
            icon_id=image_id,
        ),
    ]
    cards = [base_cards[i % len(base_cards)] for i in range(count)]
    return _sb("card_grid", {"heading": heading, "cards": cards})


def _image_card_list_block(image_id):
    return _sb(
        "image_card_list",
        {
            "heading": "Image Card List",
            "image": image_id,
            "cards": [
                {
                    "content": (
                        "<h3>First point</h3>"
                        "<p>A plain bordered text card — no icon, image or link.</p>"
                    ),
                },
                {
                    "content": (
                        "<h3>Second point</h3>"
                        "<p>The card column and the image column share a height.</p>"
                    ),
                },
                {
                    "content": (
                        "<h3>Third point</h3>"
                        "<p>Single column on mobile, two columns from md: up.</p>"
                    ),
                },
            ],
        },
    )


def _image_text_block(image_id, size="default"):
    return _sb(
        "image_text",
        {
            "image": image_id,
            "content": (
                f"<h2>Image + Text ({size})</h2><p>Freeform paragraph copy "
                "beside a square, cropped image. The heading sits inline in "
                "the text column, not above both columns.</p>"
            ),
            "size": size,
        },
    )


def _feature_panel_block(image_id, alignment, background, eyebrow="", with_cta=True):
    return _sb(
        "feature_panel",
        {
            "eyebrow": eyebrow,
            "content": f"<h2>Feature Panel ({alignment}, {background})</h2>" + _RICHTEXT_INLINE,
            "image": image_id,
            "alignment": alignment,
            "background": background,
            "link_text": "Take action" if with_cta else "",
            "link_page": None,
            "link_url": "https://example.com" if with_cta else None,
            "anchor": "",
        },
    )


def _card_carousel_block(image_id):
    """CardCarouselBlock — image is required on every carousel card."""
    return _sb(
        "card_carousel",
        {
            "content": "<h2>Card Carousel</h2>" + _RICHTEXT_INLINE,
            "link_text": "See all",
            "link_page": None,
            "link_url": "https://example.com",
            "cards": [
                _card_value(
                    f"Carousel card {n}",
                    description="Scrolls horizontally with prev/next controls.",
                    image_id=image_id,
                    tag="Campaign" if n == 1 else "",
                )
                for n in range(1, 5)
            ],
        },
    )


def _page_cards_block(index_page_id):
    return _sb(
        "page_cards",
        {
            "content": (
                "<h2>Page Cards</h2>"
                "<p>The 3 most recently published children of the chosen index page.</p>"
            ),
            "index_page": index_page_id,
            "link_text": "Read more",
        },
    )


def _accordion_block():
    return _sb(
        "accordion",
        {
            "items": [
                {"title": "What is this accordion?", "content": [_sb("text", _RICHTEXT_PARAGRAPH)]},
                {
                    "title": "How do I use it?",
                    "content": [_sb("text", "<p>Click a title to expand or collapse the panel.</p>")],
                },
                {
                    "title": "Does it support rich text?",
                    "content": [_sb("text", _RICHTEXT_KITCHEN_SINK)],
                },
            ]
        },
    )


def _callout_block(color, image_id=None, with_cta=True):
    return _sb(
        "callout",
        {
            "content": (
                f"<h2>Callout ({color})</h2>"
                "<h3>An optional sub-heading, rendered as an H3.</h3>"
            )
            + _RICHTEXT_INLINE,
            "link_text": "Take action" if with_cta else "",
            "link_page": None,
            "link_url": "https://example.com" if with_cta else None,
            "color": color,
            "image": image_id,
        },
    )


def _quote_block(image_id, alignment, with_cta=True):
    return _sb(
        "quote",
        {
            "content": (
                f"<p>Quote block with the media aligned <b>{alignment}</b>. The "
                "text sits directly on the image with a highlighter background "
                "clinging to each line.</p>"
            ),
            "image": image_id,
            "media_file": None,
            "link_text": "Learn more" if with_cta else "",
            "link_page": None,
            "link_url": "https://example.com" if with_cta else None,
            "alignment": alignment,
        },
    )


def _hero_block(banner_color, image_id=None, with_copy=True):
    return _sb(
        "hero",
        {
            "headline": f"Hero Block ({banner_color})",
            "content": _RICHTEXT_INLINE if with_copy else "",
            "image": image_id,
            "banner_color": banner_color,
        },
    )


def _donate_block_full():
    """DonateBlock with override amounts and an override URL."""
    return _sb(
        "donate",
        {
            "content": (
                "<h2>Support Our Campaign</h2>"
                "<p>Every dollar helps us reach more voters.</p>"
            ),
            "button_text": "Donate Now",
            "override_amounts": ["10.00", "25.00", "50.00", "100.00"],
            "override_url": "https://secure.actblue.com/donate/example",
        },
    )


def _donate_block_minimal():
    """DonateBlock with no overrides — falls back to Settings > Integrations."""
    return _sb(
        "donate",
        {
            "content": "<h2>Donate (using site defaults)</h2>",
            "button_text": "",
            "override_amounts": [],
            "override_url": "",
        },
    )


def _donate_fundraiseup_block(image_id):
    """
    DonateFundraiseUpBlock.

    No element_id field — every instance shows the visitor's region-specific
    Fundraise Up element, resolved client-side from the Fundraise Up
    integration's settings (Settings > Integrations). Without any region IDs
    configured there, the anchor stays hidden, which is the expected
    dev-environment rendering.
    """
    return _sb(
        "donate_fundraiseup",
        {
            "content": "<h2>Donate (Fundraise Up)</h2>" + _RICHTEXT_INLINE,
            "image": image_id,
            "image_caption": "Photo credit: placeholder",
            "designation_id": "",
        },
    )


def _signup_wagtail_forms_block(form_page_id):
    return _sb(
        "signup_wagtail_forms",
        {
            "content": "<h2>Sign Up (Wagtail Forms)</h2>" + _RICHTEXT_INLINE,
            "button_text": "Sign Up",
            "form_page": form_page_id,
            "success_message": "Thanks — you're on the list.",
        },
    )


def _success_message_stream(image_id):
    """A SuccessMessageBlock value: text + image + button."""
    return [
        _sb("text", "<h3>Thank you for signing up.</h3><p>We'll be in touch soon.</p>"),
        _sb("image", {"image": image_id, "alt_text": "", "caption": ""}),
        _sb(
            "button",
            {
                "text": "Share this",
                "link_page": None,
                "link_url": "https://example.com",
                "anchor": "",
                "style": "primary",
            },
        ),
    ]


def _signup_action_network_block(image_id, with_success=False):
    return _sb(
        "signup_action_network",
        {
            "content": "<h2>Sign Up (Action Network)</h2>" + _RICHTEXT_INLINE,
            "action_url": "https://actionnetwork.org/forms/join-30",
            "success_message": _success_message_stream(image_id) if with_success else [],
            "anchor_id": "signup-action-network" + ("-success" if with_success else ""),
        },
    )


def _signup_actionkit_block(image_id, background, with_success=False, layout="columns"):
    """
    SignupActionKitBlock.

    The block fetches its form markup from the client's live ActionKit
    instance. In dev that fetch fails and the template renders its fallback —
    which is itself worth eyeballing, and is the reason every background
    variant is included here. `layout` exercises the "side by side" (default)
    vs. "stacked vertically" outer composition -- see signup_actionkit_block.html.
    """
    return _sb(
        "signup_actionkit",
        {
            "eyebrow": "Sign the petition",
            "content": f"<h2>Sign Up (ActionKit, {background})</h2>" + _RICHTEXT_INLINE,
            "background": background,
            "layout": layout,
            "image": image_id,
            "image_caption": "Photo credit: placeholder",
            "short_form_id": "join",
            "anchor_id": f"signup-actionkit-{background}"
            + ("" if layout == "columns" else f"-{layout}"),
            "success_message": _success_message_stream(image_id) if with_success else [],
        },
    )


def _section_block(background, padding, width, anchor_id, content):
    return _sb(
        "section",
        {
            "content": content,
            "background": background,
            "padding": padding,
            "width": width,
            "anchor_id": anchor_id,
        },
    )


# ---------------------------------------------------------------------------
# Body assembly
# ---------------------------------------------------------------------------


def _content_blocks(image_id, index_page_id, form_page_id):
    """
    Every non-section block in BodyStreamBlock, in registration order, each
    preceded by a label naming it.
    """
    blocks = []

    blocks += [_heading("2. Content blocks")]

    blocks += [_label("text"), _text_block()]

    blocks += [_label("lead_text"), _lead_text_block()]

    blocks += [
        _label("image", "with alt text and caption"),
        _image_block_full(image_id),
        _label("image", "no alt text, no caption"),
        _image_block_minimal(image_id),
    ]

    blocks += [_label("video", "oEmbed URL"), _video_block()]

    blocks += [
        _label("button", "all three styles, plus an anchor link"),
        _button_block("primary", "Primary Button"),
        _button_block("secondary", "Secondary Button"),
        _button_block("outline", "Outline Button"),
        _button_block("primary", "Anchor Button (jumps to the ActionKit block)", anchor="signup-actionkit-navy"),
    ]

    blocks += [
        _label("button_group", "3 buttons — horizontal, single row"),
        _button_group_block(count=3, layout="horizontal"),
        _label("button_group", "4 buttons — horizontal, 2+2 balanced rows"),
        _button_group_block(count=4, layout="horizontal"),
        _label("button_group", "3 buttons — vertical, centered column"),
        _button_group_block(count=3, layout="vertical"),
    ]

    blocks += [
        _label("quote", "image left, with CTA"),
        _quote_block(image_id, "image-left"),
        _label("quote", "image right, no CTA"),
        _quote_block(image_id, "image-right", with_cta=False),
    ]

    blocks += [_label("raw_html"), _raw_html_block()]

    blocks += [_label("table"), _table_block()]

    blocks += [
        _label("card", "standalone, every field"),
        _card_block_full(image_id),
        _label("card", "standalone, heading only"),
        _card_block_minimal(),
    ]

    blocks += [
        _label("person_card", "every field"),
        _person_card_block_full(image_id),
        _label("person_card", "name only"),
        _person_card_block_minimal(),
    ]

    blocks += [
        _label("person_card_grid", "5 people — 3+2 row split"),
        _person_card_grid_block(image_id, count=5, heading="Person Card Grid (5 people)"),
        _label("person_card_grid", "7 people — 3+2+2, no orphan row"),
        _person_card_grid_block(image_id, count=7, heading="Person Card Grid (7 people)"),
    ]

    blocks += [
        _label("card_grid", "3 cards — three-column layout"),
        _card_grid_block(image_id, count=3, heading="Card Grid (3 cards)"),
        _label("card_grid", "4 cards — 2x2 layout"),
        _card_grid_block(image_id, count=4, heading="Card Grid (4 cards)"),
        _label("card_grid", "7 cards — 3+2+2, no orphan row"),
        _card_grid_block(image_id, count=7, heading="Card Grid (7 cards)"),
    ]

    blocks += [_label("image_grid", "5 images"), _image_grid_block(image_id, count=5)]

    blocks += [_label("logo_grid", "6 logos, some linked"), _logo_grid_block(image_id, count=6)]

    blocks += [_label("image_card_list"), _image_card_list_block(image_id)]

    blocks += [
        _label("image_text", "small"),
        _image_text_block(image_id, size="small"),
        _label("image_text", "default"),
        _image_text_block(image_id, size="default"),
        _label("image_text", "large"),
        _image_text_block(image_id, size="large"),
    ]

    blocks += [
        _label("feature_panel", "image left, light, with eyebrow"),
        _feature_panel_block(image_id, "image-left", "white", eyebrow="Featured Campaign"),
        _label("feature_panel", "image right, dark, no eyebrow"),
        _feature_panel_block(image_id, "image-right", "dark-grey"),
        _label("feature_panel", "image left, 350 blue, no CTA"),
        _feature_panel_block(image_id, "image-left", "blue-gradient", with_cta=False),
    ]

    blocks += [_label("card_carousel"), _card_carousel_block(image_id)]

    blocks += [_label("page_cards", "children of the generated index page"), _page_cards_block(index_page_id)]

    blocks += [_label("accordion"), _accordion_block()]

    blocks += [_label("callout", "one per background colour")]
    for color in _BACKGROUND_KEYS:
        blocks.append(_callout_block(color))
    blocks += [
        _label("callout", "with a background image, no CTA"),
        _callout_block("navy", image_id=image_id, with_cta=False),
    ]

    blocks += [_label("hero", "one per background colour, with image")]
    for color in _BACKGROUND_KEYS:
        blocks.append(_hero_block(color, image_id=image_id))
    blocks += [
        _label("hero", "headline only — no copy, no image"),
        _hero_block("navy", with_copy=False),
    ]

    blocks += [_heading("3. Action blocks")]

    blocks += [
        _label("donate", "override amounts and URL"),
        _donate_block_full(),
        _label("donate", "site defaults"),
        _donate_block_minimal(),
    ]

    blocks += [_label("donate_fundraiseup"), _donate_fundraiseup_block(image_id)]

    blocks += [_label("signup_wagtail_forms"), _signup_wagtail_forms_block(form_page_id)]

    blocks += [
        _label("signup_action_network"),
        _signup_action_network_block(image_id),
        _label("signup_action_network", "with a custom success message"),
        _signup_action_network_block(image_id, with_success=True),
    ]

    blocks += [_label("signup_actionkit", "one per background colour")]
    for background in _BACKGROUND_KEYS:
        blocks.append(_signup_actionkit_block(image_id, background))
    blocks += [
        _label("signup_actionkit", "with a custom success message"),
        _signup_actionkit_block(image_id, "navy", with_success=True),
    ]
    blocks += [
        _label("signup_actionkit", "stacked vertically layout"),
        _signup_actionkit_block(image_id, "dark-grey", layout="vertical"),
    ]

    return blocks


def _section_blocks(image_id):
    """
    SectionBlock permutations: every background, every padding, every width.

    Inner content is a compact but representative mix — enough to check that a
    dark fill inverts text, buttons, tables and cards, without repeating the
    whole block catalogue six times.
    """
    blocks = [_heading("4. Sections")]

    def inner():
        return [
            _sb("text", "<h2>Section heading</h2>" + _RICHTEXT_PARAGRAPH),
            _button_block("primary", "Primary Button"),
            _button_block("outline", "Outline Button"),
            _table_block(),
            _accordion_block(),
            _card_grid_block(image_id, count=3, heading=""),
        ]

    for background in _BACKGROUND_KEYS:
        blocks.append(_label("section", f"background: {background}, padding: md, width: default"))
        blocks.append(
            _section_block(background, "md", "default", f"section-{background}", inner())
        )

    for padding in ("sm", "lg"):
        blocks.append(_label("section", f"padding: {padding}"))
        blocks.append(
            _section_block(
                "light-grey",
                padding,
                "default",
                f"section-padding-{padding}",
                [
                    _sb("text", f"<h2>Padding: {padding}</h2>" + _RICHTEXT_PARAGRAPH),
                    _image_block_minimal(image_id),
                ],
            )
        )

    for width in ("narrow", "wide"):
        blocks.append(_label("section", f"width: {width}"))
        blocks.append(
            _section_block(
                "white",
                "md",
                width,
                f"section-width-{width}",
                [
                    _sb("text", f"<h2>Width: {width}</h2>" + _RICHTEXT_PARAGRAPH),
                    _image_block_minimal(image_id),
                    _accordion_block(),
                ],
            )
        )

    return blocks


def _timeline_accordion_block(image_id):
    """
    A "victories at a glance"-style accordion, one item per
    AccordionItemContentBlock block type so all are exercised: an image
    item and a video item, plus a plain text-only item (the real
    /our-impact data's 83 items split 67/15/1 across image/video/neither --
    AccordionItemContentBlock expresses "neither" as simply having no such
    block in the content list, not a present-but-blank field).
    """
    return _sb(
        "accordion",
        {
            "items": [
                {
                    "title": "A victory with an image",
                    "content": [
                        _sb("text", "<p>Short description of what happened.</p>"),
                        _sb("image", {"image": image_id, "alt_text": "", "caption": ""}),
                    ],
                },
                {
                    "title": "A victory with a video",
                    "content": [
                        _sb("text", "<p>Short description of what happened.</p>"),
                        _sb(
                            "video",
                            {
                                "embed_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                                "media_file": None,
                                "caption": "",
                            },
                        ),
                    ],
                },
                {
                    "title": "A text-only victory",
                    "content": [_sb("text", _RICHTEXT_PARAGRAPH)],
                },
            ]
        },
    )


def _timeline_block(image_id):
    """
    TimelineBlock: two years, each "basically a section" — a freely
    composed TimelineYearContentBlock stream, per the block's own design.
    The year-jump nav at the top is derived from these years at render
    time, not built here.
    """
    return _sb(
        "timeline",
        {
            "years": [
                {
                    "year": "2019",
                    "content": [
                        _sb("text", "<h2>Millions strike for the climate</h2>" + _RICHTEXT_PARAGRAPH),
                        _image_block_minimal(image_id),
                        _timeline_accordion_block(image_id),
                    ],
                },
                {
                    "year": "2021",
                    "content": [
                        _sb("text", "<h2>Keystone XL is cancelled</h2>" + _RICHTEXT_PARAGRAPH),
                    ],
                },
            ]
        },
    )


def _timeline_blocks(image_id):
    return [_label("timeline"), _timeline_block(image_id)]


def _build_body(image_id, index_page_id, form_page_id):
    return (
        _typography_blocks()
        + _content_blocks(image_id, index_page_id, form_page_id)
        + _section_blocks(image_id)
        + _timeline_blocks(image_id)
    )


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = "Create a test ContentPage exercising every block type. DEBUG=True only."

    def add_arguments(self, parser):
        parser.add_argument(
            "--slug",
            default="test-blocks",
            help="Slug for the test page (default: test-blocks).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Delete and recreate the page if it already exists.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "create_test_page only runs in DEBUG=True. "
                "Do not run this on production."
            )

        # Deferred imports to avoid import-time DB access (architecture rule #4).
        from wagtail.models import Page, Site  # noqa: F401

        from wtrx.blocks import BACKGROUND_COLOR_CHOICES, BodyStreamBlock
        from wtrx.models import ContentPage, FormField, FormPage, IndexPage

        slug = options["slug"]
        force = options["force"]

        # Fail loudly if the palette has grown since this command was written,
        # rather than silently omitting a colour from the QA page.
        palette = [key for key, _label_text in BACKGROUND_COLOR_CHOICES]
        if palette != _BACKGROUND_KEYS:
            raise CommandError(
                "BACKGROUND_COLOR_CHOICES has changed since create_test_page was "
                f"last updated.\n  blocks.py: {palette}\n  command:   {_BACKGROUND_KEYS}\n"
                "Update _BACKGROUND_KEYS in this command to match."
            )

        try:
            site = Site.objects.get(is_default_site=True)
        except Site.DoesNotExist:
            raise CommandError(
                "No default Site found. Run 'python manage.py setup_site' first."
            )

        parent = site.root_page.specific

        existing = ContentPage.objects.filter(slug=slug).first()
        if existing:
            if force:
                self.stdout.write(f'  Deleting existing page "{existing.title}" …')
                existing.delete()
                # Refresh parent so treebeard's numchild counter reflects the
                # deletion; without this add_child() crashes when parent has
                # no remaining children (numchild=0 expected but stale in memory).
                parent.refresh_from_db()
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'  Page with slug "{slug}" already exists (pk={existing.pk}). '
                        f"Use --force to overwrite."
                    )
                )
                return

        image = _make_test_image()

        # The page has to exist before its supporting children can be attached,
        # and their pks are needed to build the body — so create it empty first
        # and fill the body in afterwards.
        page = ContentPage(
            title="Block Test Page",
            slug=slug,
            hero_headline="Block Test Page",
            hero_copy=(
                "<p>Every block type in BodyStreamBlock, plus a typography "
                "reference. This page is generated by "
                "<b>manage.py create_test_page</b> and is DEBUG-only.</p>"
            ),
            hero_banner_color="navy",
            body="[]",
        )
        parent.add_child(instance=page)

        index_page = self._make_index_page(page, IndexPage, ContentPage)
        form_page = self._make_form_page(page, FormPage, FormField)

        body_data = _build_body(image.pk, index_page.pk, form_page.pk)
        page.body = json.dumps(body_data)
        page.save()

        self._report(page, body_data, BodyStreamBlock, slug)

    # -- supporting fixtures -------------------------------------------------

    def _make_index_page(self, parent, IndexPage, ContentPage):
        """
        An IndexPage with three published children, for PageCardsBlock to list.

        first_published_at is set explicitly: Wagtail only populates it when a
        page is published through the admin, and PageCardsBlock orders by it
        (see AGENTS.md pitfall #32).
        """
        index_page = IndexPage(
            title="Block Test Index",
            slug="block-test-index",
            hero_headline="Block Test Index",
            intro="<p>Child pages of this index feed the Page Cards block.</p>",
            body="[]",
        )
        parent.add_child(instance=index_page)

        now = timezone.now()
        for n in range(1, 4):
            child = ContentPage(
                title=f"Index Child Page {n}",
                slug=f"block-test-index-child-{n}",
                hero_headline=f"Index Child Page {n}",
                hero_copy="<p>A child page used to populate the Page Cards block.</p>",
                body="[]",
                first_published_at=now - timedelta(days=n),
                last_published_at=now - timedelta(days=n),
            )
            index_page.add_child(instance=child)

        return index_page

    def _make_form_page(self, parent, FormPage, FormField):
        """A FormPage with two fields, for SignupWagtailFormsBlock to render."""
        form_page = FormPage(
            title="Block Test Form",
            slug="block-test-form",
            intro="<p>A form rendered inline by the Sign Up (Wagtail Forms) block.</p>",
            thank_you_text="<p>Thanks for signing up.</p>",
            from_address="noreply@example.com",
            to_address="test@example.com",
            subject="Block test form submission",
        )
        parent.add_child(instance=form_page)

        FormField.objects.create(
            page=form_page,
            sort_order=0,
            label="Email",
            field_type="email",
            required=True,
        )
        FormField.objects.create(
            page=form_page,
            sort_order=1,
            label="Full name",
            field_type="singleline",
            required=True,
        )
        return form_page

    # -- reporting -----------------------------------------------------------

    def _report(self, page, body_data, BodyStreamBlock, slug):
        """Print a summary, and warn about any registered block left untested."""
        used = set()

        def walk(entries):
            for entry in entries:
                used.add(entry["type"])
                value = entry.get("value")
                if entry["type"] == "section" and isinstance(value, dict):
                    walk(value.get("content", []))

        walk(body_data)

        registered = set(BodyStreamBlock().child_blocks.keys())
        missing = sorted(registered - used)

        self.stdout.write(
            self.style.SUCCESS(
                f'  Created test page "{page.title}" (pk={page.pk}) at /{slug}/'
            )
        )
        self.stdout.write(
            f"  {len(body_data)} top-level blocks, "
            f"{len(used & registered)}/{len(registered)} block types covered."
        )
        if missing:
            self.stdout.write(
                self.style.WARNING(
                    "  Blocks registered in BodyStreamBlock but NOT on the test "
                    "page: " + ", ".join(missing) + "\n"
                    "  Add a builder for each in create_test_page.py."
                )
            )
        self.stdout.write(f"  Visit: http://localhost:8000/{slug}/")

"""
StreamField blocks for the BodyStreamBlock.

Block categories (in definition order):
  Content:  TextBlock, ImageBlock, VideoBlock, ButtonBlock, ButtonGroupBlock,
            RawHTMLBlock, TableBlock
  Cards:    CardBlock, CarouselCardBlock, PersonCardBlock
  Layout:   AccordionItemBlock, CardGridBlock, ImageGridItemBlock,
            ImageGridBlock, LogoGridItemBlock, LogoGridBlock,
            PersonCardGridBlock, ImageCardListItemBlock,
            ImageCardListBlock, ImageTextBlock, FeaturePanelBlock,
            CardCarouselBlock, PageCardsBlock, AccordionBlock, QuoteBlock,
            CalloutBlock
  Actions:  DonateBlock, SignupWagtailFormsBlock, SignupActionNetworkBlock,
            SignupActionKitBlock, SignupLinkBlock
  Layout²:  AnnouncementBarBlock, HeroCTABlock, HeroBlock, SectionBlock
            (defined after action blocks so their nested/optional fields
            can instantiate the action block classes)

All blocks are assembled into BodyStreamBlock at the bottom of this file.
"""

import copy
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
from urllib.parse import urlparse

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from wagtail.blocks import (
    CharBlock,
    ChoiceBlock,
    DecimalBlock,
    EmailBlock,
    ListBlock,
    PageChooserBlock,
    RichTextBlock,
    StreamBlock,
    StructBlock,
    StructBlockValidationError,
    TextBlock as WagtailTextBlock,
    URLBlock,
)
from wagtail.blocks import RawHTMLBlock as WagtailRawHTMLBlock
from wagtail.contrib.table_block.blocks import TableBlock as WagtailTableBlock
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import Site
from wagtail_ai.blocks import ai_image_block
from wagtailmedia.blocks import VideoChooserBlock

from wtrx.constants import (
    RICHTEXT_FEATURES_FULL,
    RICHTEXT_FEATURES_HEADING_H2,
    RICHTEXT_FEATURES_HEADING_H3,
    RICHTEXT_FEATURES_HEADINGS_H2_H3,
    RICHTEXT_FEATURES_INLINE,
)
from wtrx.integrations import actionkit
from wtrx.site_settings import IntegrationSettings

# ---------------------------------------------------------------------------
# Choice constants
# ---------------------------------------------------------------------------

BUTTON_STYLE_CHOICES = [
    ("primary", _("Primary")),
    ("secondary", _("Secondary")),
    ("outline", _("Outline")),
]

# Shared by every block that puts an image in a side column and lets the
# editor flip which side it's on: QuoteBlock, FeaturePanelBlock,
# ImageCardListBlock, ImageTextBlock, DonateFundraiseUpBlock. Each of these
# used to define its own identical list (or, for the latter three, no
# alignment field at all) — one shared constant here, following the same
# "reuse rather than duplicate" precedent as BACKGROUND_COLOR_CHOICES below.
IMAGE_ALIGNMENT_CHOICES = [
    ("image-left", _("Image left")),
    ("image-right", _("Image right")),
]

# ---------------------------------------------------------------------------
# Background palette
# ---------------------------------------------------------------------------
#
# One palette, offered identically by every block that has a background
# choice: SectionBlock, CalloutBlock, FeaturePanelBlock, HeroBlock /
# HeroMixin's banner variant, and SignupActionKitBlock. Each of those used to
# carry its own list — Section offered light/dark/primary/secondary/muted,
# the feature panel only light/dark, signup spelled dark grey "dark" — so
# the same visual decision was made from a different vocabulary depending on
# which block an editor happened to be standing in. There is one list now,
# and a block that grows a background field should reuse it rather than
# define a sixth.
#
# The colors are Figma's callout/hero swatches plus White, which the old
# Section list called "light" and which a section sitting on the page
# background still needs. See main.css's .wtr-bg-{color} classes for the
# token behind each key.
BACKGROUND_COLOR_CHOICES = [
    ("white", _("White")),
    ("light-grey", _("Light grey")),
    ("dark-grey", _("Dark grey")),
    ("navy", _("Navy")),
    ("red", _("Red")),
    ("blue-gradient", _("350 Blue")),
]

BACKGROUND_COLOR_KEYS = {value for value, _label in BACKGROUND_COLOR_CHOICES}

# The fills light enough to need dark text, a dark-outline button and an
# inverted eyebrow pill; every other color in the palette is dark enough for
# light (white) text. Block templates branch on this one set via the
# `background_is_light` filter instead of testing color keys inline, so
# adding a light color to the palette never means hunting down a scattered
# `== 'light-grey'` check in five templates.
LIGHT_BACKGROUND_COLORS = {"white", "light-grey"}

# Keys that predate the shared palette and may still be sitting in
# StreamField content. A data migration rewrites the ones it can reach, but a
# legacy value can also arrive from an old page revision (Wagtail stores each
# revision as its own JSON blob, and reverting to one re-publishes that JSON
# verbatim), so resolution stays in the render path permanently rather than
# being a one-shot fixup.
LEGACY_BACKGROUND_VALUES = {
    "light": "white",            # SectionBlock, FeaturePanelBlock
    "dark": "dark-grey",         # SectionBlock, FeaturePanelBlock, SignupActionKitBlock
    "muted": "light-grey",       # SectionBlock
    "primary": "blue-gradient",  # SectionBlock
    "secondary": "navy",         # SectionBlock
}

SECTION_PADDING_CHOICES = [
    ("sm", _("Small")),
    ("md", _("Medium")),
    ("lg", _("Large")),
]

# How wide a section's inner content column is. Figma draws sections at three
# distinct measures rather than one: a 1266px media/full-width band (The Great
# Power Shift's video section), the shared 1152px default, and an 800px reading
# column for text + accordion stacks (that page's "Get the full picture."). The
# section owns this rather than each child block, because every child in a
# section shares one left edge — a narrow accordion inside a default-width
# section would sit 176px right of the heading above it.
SECTION_WIDTH_CHOICES = [
    ("narrow", _("Narrow (800px)")),
    ("default", _("Default (1152px)")),
    ("wide", _("Wide (1266px)")),
]


HERO_LAYOUT_CHOICES = [
    ("centered", _("Centered")),
    ("left", _("Left-aligned")),
]

# Mapping of Action Network URL path segments (plural) to embed types (singular).
# Only 'forms' is supported initially; others will be added as needed.
ACTION_NETWORK_URL_TYPES = {
    "forms": "form",
}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def resolve_background(value, default="white"):
    """
    Map a stored background key onto its BACKGROUND_COLOR_CHOICES key.

    Translates the pre-palette keys listed in LEGACY_BACKGROUND_VALUES, and
    falls back to `default` for anything unrecognised — a background is
    decorative, so an unreadable value should render the plain fill rather
    than emit a `.wtr-bg-` class that matches no rule and leaves the panel
    transparent with light text on it.
    """
    key = LEGACY_BACKGROUND_VALUES.get(value, value)
    return key if key in BACKGROUND_COLOR_KEYS else default


def background_is_light(value):
    """True when `value` names a fill that needs dark text rather than light."""
    return resolve_background(value) in LIGHT_BACKGROUND_COLORS


def parse_action_network_url(url):
    """
    Parse an Action Network URL and return ``{'action_type': ..., 'slug': ...}``.

    Accepted formats:
      - https://actionnetwork.org/forms/my-form-slug
      - https://actionnetwork.org/forms/my-form-slug?source=direct_link&
      - https://www.actionnetwork.org/forms/my-form-slug/

    Raises ``ValidationError`` with a user-friendly message if the URL is not
    a valid Action Network form URL.
    """
    parsed = urlparse(url)

    # Validate hostname
    hostname = (parsed.hostname or "").lower()
    if hostname not in ("actionnetwork.org", "www.actionnetwork.org"):
        raise ValidationError(
            _(
                "This does not appear to be an Action Network URL. "
                "Expected a URL like https://actionnetwork.org/forms/your-form-slug"
            )
        )

    # Split path into non-empty segments
    segments = [s for s in parsed.path.strip("/").split("/") if s]
    if len(segments) < 2:
        raise ValidationError(
            _(
                "Could not find a form slug in this URL. "
                "Expected a URL like https://actionnetwork.org/forms/your-form-slug"
            )
        )

    url_type = segments[0].lower()
    slug = segments[1]

    if url_type not in ACTION_NETWORK_URL_TYPES:
        supported = ", ".join(sorted(ACTION_NETWORK_URL_TYPES.keys()))
        raise ValidationError(
            _(
                "Unsupported Action Network action type '%(url_type)s'. "
                "Currently supported: %(supported)s."
            ),
            params={"url_type": url_type, "supported": supported},
        )

    # Validate slug format — AN slugs are lowercase alphanumeric + hyphens.
    # This also prevents injection via the slug into template JS/HTML contexts.
    if not re.match(r"^[a-z0-9][a-z0-9\-]*$", slug):
        raise ValidationError(
            _("The URL slug '%(slug)s' contains unexpected characters."),
            params={"slug": slug},
        )

    return {
        "action_type": ACTION_NETWORK_URL_TYPES[url_type],
        "slug": slug,
    }


def _validate_at_most_one_link(cleaned, errors, extra_fields=()):
    """
    Raise if more than one link target is set.

    The base pair is link_page/link_url, which every caller has.
    ``extra_fields`` names further link fields a block also offers —
    FeaturePanelBlock passes ("anchor",) — so a block that gained a third
    target does not need its own copy of this check. Blocks that pass
    nothing keep the original two-field message verbatim.

    Modifies the errors dict in place and returns it.
    """
    fields = ("link_page", "link_url", *extra_fields)
    set_fields = [name for name in fields if cleaned.get(name)]
    if len(set_fields) > 1:
        if extra_fields:
            msg = ValidationError(
                _("Provide only one of link page, link URL, or anchor.")
            )
        else:
            msg = ValidationError(
                _("Provide either a link page or a link URL, not both.")
            )
        for name in set_fields:
            errors[name] = msg
    return errors


# ---------------------------------------------------------------------------
# Content blocks
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Block previews
#
# Wagtail renders the block picker's preview by server-side rendering the block
# with a placeholder value (`Meta.preview_value`) through the global preview
# template at templates/wagtailcore/shared/block_preview.html. A block only
# becomes previewable once it declares `preview_value` -- see that template's
# comment for the full contract. `Meta.description` is shown as prose beside
# the preview, and is worth setting even on blocks with no preview.
#
# Keep preview values realistic but obviously fake: they are what an editor
# sees when deciding which block to reach for.
# ---------------------------------------------------------------------------


PREVIEW_DATA_PATH = Path(__file__).resolve().parent.parent / "previews" / "block_previews.json"


@lru_cache(maxsize=1)
def _preview_data():
    """
    Load the harvested block-preview values, keyed by block name.

    Regenerate with `python manage.py harvest_block_previews`. Cached for the
    process lifetime: this reads a file, never the database, so it is safe to
    call from `is_previewable` (which Wagtail evaluates while building the
    picker). A missing file simply means no content-sourced previews.
    """
    try:
        return json.loads(PREVIEW_DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class ContentPreviewMixin:
    """
    Sources a block's picker preview from real site content.

    Mix into any block whose preview should come from
    `wtrx/previews/block_previews.json` rather than a hand-written
    `Meta.preview_value`. The two are alternatives -- use this mixin when real
    content exists for the block, and `Meta.preview_value` when it doesn't.

    Two details make this work:

    - The harvested JSON is in `get_prep_value()` form, where an image is a
      bare pk. `Block.normalize()` (which `get_preview_value` would otherwise
      apply) does NOT turn a pk back into an image -- only `to_python()` does,
      so that is what this uses. Skipping it renders an int where a template
      expects an image.
    - Overriding `get_preview_value` is itself what Wagtail's default
      `is_previewable` looks for, so it would mark *every* mixed-in block as
      previewable even with no data behind it, producing blank previews.
      `is_previewable` is therefore pinned to "do we actually have data".
    """

    #: Key into the harvested JSON. Defaults to the block's name in its parent
    #: StreamBlock, which is what the harvester keys on.
    preview_key = None

    #: Optional ``{field_name: count}`` caps applied to list fields in the
    #: harvested value. Real content is not always the clearest preview: a
    #: CardGridBlock with exactly four cards deliberately lays out 2x2 rather
    #: than in three columns, so its preview trims to three to show the layout
    #: an editor gets by default. Trimming beats hand-authoring the block --
    #: the copy and images stay real.
    preview_max_items = {}

    def _harvested_preview(self):
        entry = self._harvested_entry()
        return entry.get("value") if entry else None

    def _harvested_entry(self):
        key = self.preview_key or getattr(self, "name", None)
        return _preview_data().get(key) if key else None

    def get_preview_value(self):
        raw = self._harvested_preview()
        if raw is None:
            return super().get_preview_value()
        raw = copy.deepcopy(raw)
        for field, limit in self.preview_max_items.items():
            if isinstance(raw.get(field), list):
                raw[field] = raw[field][:limit]
        repaired, _ = _repair_image_references(self, raw)
        return self.to_python(repaired)

    @property
    def is_previewable(self):
        # Deliberately a plain property, unlike Wagtail's cached_property.
        # Wagtail shares one block instance across every StreamBlock that
        # declares it, so a cached value computed from database state would be
        # frozen process-wide -- an image library that fills up later would
        # never start offering previews. The queries behind it are cached
        # below, and this only runs while building the admin block picker.
        raw = self._harvested_preview()
        if raw is None:
            return False
        # An image-dependent block with nothing to show would render a broken
        # preview rather than a degraded one -- better to offer none at all.
        _, images_ok = _repair_image_references(self, copy.deepcopy(raw))
        return images_ok


def _repair_image_references(block, raw):
    """
    Swap any image pk in harvested preview data that no longer resolves for one
    that does, in place, returning `raw`.

    Harvested previews store images the way StreamField does -- as a primary
    key -- and those keys only mean anything in the database they came from. A
    fresh clone, CI, or a re-imported library leaves them dangling, and
    `to_python()` turns a dangling pk into None. That is not a harmless blank:
    block templates reasonably assume a required image is present (see
    image_block.html, which calls `{% image %}` with no None-guard because the
    field cannot be empty in real content), so the preview breaks rather than
    degrading. Substituting any real image keeps the preview representative.

    Walks the block tree rather than the raw data alone, because only the block
    definition says which values are image references and which are ordinary
    integers.
    """
    from wagtail.images.blocks import ImageChooserBlock

    def resolve(block, raw):
        if isinstance(raw, dict) and hasattr(block, "child_blocks"):
            for name, value in raw.items():
                child = block.child_blocks.get(name)
                if child is None:
                    continue
                if isinstance(child, ImageChooserBlock):
                    if value and not _image_exists(value):
                        raw[name] = _fallback_image_pk()
                        if raw[name] is None:
                            unsatisfied.append(name)
                else:
                    resolve(child, value)
        elif isinstance(raw, list):
            for item in raw:
                # ListBlock items are bare values; StreamBlock children are
                # {type, value, id} dicts naming the child block to use.
                if hasattr(block, "child_block"):
                    resolve(block.child_block, item)
                elif isinstance(item, dict) and "type" in item:
                    child = getattr(block, "child_blocks", {}).get(item["type"])
                    if child is not None:
                        resolve(child, item.get("value"))

    unsatisfied = []
    resolve(block, raw)
    return raw, not unsatisfied


#: Preview lookups run once per block while rendering the picker, so the
#: handful of queries behind them are cached briefly rather than per request.
#: Short enough that a newly-populated image library starts working promptly.
PREVIEW_LOOKUP_CACHE_TIMEOUT = 60


def _image_exists(pk):
    from wtrx.images import CustomImage

    key = "wtrx:preview_image_exists:%s" % pk
    cached = cache.get(key)
    if cached is None:
        cached = CustomImage.objects.filter(pk=pk).exists()
        cache.set(key, cached, PREVIEW_LOOKUP_CACHE_TIMEOUT)
    return cached


def _fallback_image_pk():
    key = "wtrx:preview_fallback_image"
    cached = cache.get(key)
    if cached is None:
        image = preview_image()
        cached = image.pk if image else 0
        cache.set(key, cached, PREVIEW_LOOKUP_CACHE_TIMEOUT)
    return cached or None


def preview_image(min_width=800):
    """
    Return an arbitrary image from the library, for use as a `preview_value`
    placeholder on blocks with an ImageChooserBlock field.

    MUST only be called at request time -- from inside a `preview_value`
    callable, never at import time (AGENTS.md "Common Pitfalls" #1).

    Returns None on an empty image library. Callers must handle that: block
    templates do NOT all tolerate a missing image (image_block.html calls
    `{% image %}` unguarded, since its field is required in real content), so a
    None here means "do not offer a preview", not "preview without the image".
    """
    from wtrx.images import CustomImage

    return (
        CustomImage.objects.filter(width__gte=min_width).order_by("pk").first()
        or CustomImage.objects.order_by("pk").first()
    )


def _hero_preview_value():
    """Placeholder value for HeroBlock's picker preview."""
    return {
        "headline": _("A future powered by people"),
        "content": "<p>Supporting copy introducing the section that follows.</p>",
        "image": preview_image(),
        "banner_color": "navy",
    }


def _person_card_preview_value():
    """Placeholder value for PersonCardBlock's picker preview."""
    return {
        "name": _("Jane Doe"),
        "role": _("Regional Organising Lead"),
        "image": preview_image(),
        "bio": _(
            "Jane coordinates campaign partners across the region and has "
            "organised with the climate movement for over a decade."
        ),
        "email": "jane@example.org",
    }


def _image_grid_preview_value():
    """
    Placeholder value for ImageGridBlock's picker preview. Not
    ContentPreviewMixin: no real page uses this brand-new block yet, so
    there is nothing to harvest -- see preview_image()'s docstring for why
    a hand-written preview_value is the right tool here, same as
    HeroBlock/PersonCardBlock above. Reuses the one placeholder image
    across all four slots, same as any hand-authored multi-image preview
    in this file.
    """
    img = preview_image()
    return {
        "heading": "",
        "images": [{"image": img, "alt_text": ""} for _i in range(4)],
    }


def _logo_grid_preview_value():
    """
    Placeholder value for LogoGridBlock's picker preview.

    Uses real partner-logo images already in the media library where
    available (title contains "logo", excluding "350" -- that's the
    site's own brand mark, not a partner) rather than repeating one
    arbitrary image four times the way preview_image() alone would: a
    logo grid specifically reads better with genuinely different marks
    side by side, since the whole point is showing several organizations
    at once. Falls back to preview_image() -- repeated, same as any other
    hand-authored multi-image preview in this file -- when the library
    doesn't have enough logo-titled images (e.g. a fresh dev DB with no
    fixture data).

    Deduplicates by title before capping at 7: the fixture library has at
    least one logo re-uploaded under an identical title (Wagtail suffixes
    the file name on a duplicate upload but leaves the title alone), which
    would otherwise show the same mark twice in the preview.
    """
    from wtrx.images import CustomImage

    candidates = (
        CustomImage.objects.filter(title__icontains="logo")
        .exclude(title__icontains="350")
        .order_by("pk")[:20]
    )
    seen_titles = set()
    logos = []
    for img in candidates:
        if img.title in seen_titles:
            continue
        seen_titles.add(img.title)
        logos.append(img)
        if len(logos) == 7:
            break
    if len(logos) < 2:
        fallback = preview_image()
        logos = [fallback] * 4
    return {
        "heading": "",
        "logos": [
            {
                "image": img,
                "name": _("Partner Organization %(n)d") % {"n": i + 1},
                "link_page": None,
                "link_url": "",
            }
            for i, img in enumerate(logos)
        ],
    }


def _person_card_grid_preview_value():
    """
    Placeholder value for PersonCardGridBlock's picker preview. Five
    people demonstrates the 3+2 row split -- see _balanced_rows().
    """
    img = preview_image()
    return {
        "heading": "",
        "people": [
            {
                "name": _("Jane Doe"),
                "role": _("Regional Organising Lead"),
                "image": img,
                "bio": "",
                "email": "",
                "phone": "",
                "website": "",
            }
            for _i in range(5)
        ],
    }


def _signup_wagtail_forms_preview_value():
    """
    Placeholder value for SignupWagtailFormsBlock's picker preview.

    `form_page` is required on the block, but a site need not have built a Form
    page yet -- and there is nothing sensible to invent, since the fields come
    from whichever page is chosen. Falls back to None, which the template
    renders as the surrounding prompt without a form body.
    """
    from wtrx.models import FormPage

    return {
        "content": (
            "<h2>Sign up for updates</h2>"
            "<p>Tell us where to reach you and we will keep you posted.</p>"
        ),
        "button_text": _("Sign up"),
        "form_page": FormPage.objects.live().first(),
    }


class TextBlock(ContentPreviewMixin, RichTextBlock):
    """
    A rich text content block.

    Allows: bold, italic, links, ordered/unordered lists, and headings h2–h4.
    No StructBlock wrapper — the value IS the rich text.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("features", RICHTEXT_FEATURES_FULL)
        super().__init__(**kwargs)

    class Meta:
        icon = "pilcrow"
        label = _("Text")
        template = "wtrx/components/streamfield/blocks/text_block.html"
        description = _(
            "Rich text: paragraphs, headings, lists, bold/italic and links. "
            "The default choice for ordinary body copy."
        )


class LeadTextBlock(RichTextBlock):
    """
    A short lead-in paragraph, rendered larger than ordinary body copy.

    Restricted to RICHTEXT_FEATURES_INLINE (no headings/lists/blockquote) —
    a lead paragraph is a single opening statement; TextBlock already covers
    longer structured copy.

    Deliberately NOT ContentPreviewMixin (AGENTS.md pitfall #45): no real
    page uses this block yet, so there is nothing in
    wtrx/previews/block_previews.json to harvest, and that mixin's
    is_previewable ignores Meta.preview_value entirely -- it would leave
    this block with no picker preview at all. Plain Wagtail preview_value is
    a full alternative here since, unlike an image-bearing block, nothing
    needs to be looked up at request time.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("features", RICHTEXT_FEATURES_INLINE)
        super().__init__(**kwargs)

    class Meta:
        icon = "pilcrow"
        label = _("Lead paragraph")
        template = "wtrx/components/streamfield/blocks/lead_text_block.html"
        description = _(
            "A larger introductory paragraph for opening a page or section. "
            "Bold/italic/links only — use a regular Text block for headings "
            "or lists."
        )
        # preview_value must live on Meta, not the block class itself --
        # Wagtail's default get_preview_value()/is_previewable() only ever
        # look at self.meta.preview_value (AGENTS.md pitfall #45).
        preview_value = _(
            "<p>A short, larger opening statement that sits above the "
            "regular body copy.</p>"
        )


@ai_image_block()
class ImageBlock(ContentPreviewMixin, StructBlock):
    """
    An image with optional alt text override and caption.

    When alt_text is blank the rendition's own alt is used, which is the
    image's description falling back to its title (Wagtail's
    ``default_alt_text``) — never the raw filename if a description is set.
    Decorated with wagtail-ai's ai_image_block() (default field names match:
    "image"/"alt_text") to add a "generate alt text from image" button in
    the admin.
    """

    image = ImageChooserBlock(label=_("Image"))
    alt_text = CharBlock(
        required=False,
        label=_("Alt text"),
        help_text=_(
            "Overrides the image description for screen readers. "
            "Leave blank to use the description set on the image itself."
        ),
    )
    caption = CharBlock(
        required=False,
        label=_("Caption"),
        help_text=_("Optional caption displayed below the image."),
    )

    class Meta:
        icon = "image"
        label = _("Image")
        template = "wtrx/components/streamfield/blocks/image_block.html"


class VideoBlock(ContentPreviewMixin, StructBlock):
    """
    A video block supporting either an embed URL (YouTube, Vimeo, etc.)
    or an uploaded media file via wagtailmedia.

    Exactly one of embed_url or media_file must be set. clean() enforces this.
    """

    embed_url = URLBlock(
        required=False,
        label=_("Embed URL"),
        help_text=_("YouTube, Vimeo, or other oEmbed-compatible URL."),
    )
    media_file = VideoChooserBlock(
        required=False,
        label=_("Media file"),
        help_text=_("An uploaded video file from the media library."),
    )
    caption = CharBlock(
        required=False,
        label=_("Caption"),
    )

    def clean(self, value):
        cleaned = super().clean(value)
        errors = {}
        has_embed = bool(cleaned.get("embed_url"))
        has_file = bool(cleaned.get("media_file"))
        if not has_embed and not has_file:
            msg = ValidationError(_("Provide either an embed URL or a media file."))
            errors["embed_url"] = msg
            errors["media_file"] = msg
        elif has_embed and has_file:
            msg = ValidationError(
                _("Provide either an embed URL or a media file, not both.")
            )
            errors["embed_url"] = msg
            errors["media_file"] = msg
        if errors:
            raise StructBlockValidationError(block_errors=errors)
        return cleaned

    class Meta:
        icon = "media"
        label = _("Video")
        template = "wtrx/components/streamfield/blocks/video_block.html"


class ButtonBlock(StructBlock):
    """
    A CTA button with text, style, and exactly one link target.

    Exactly one of link_page, link_url or anchor must be set. clean()
    enforces this.

    `anchor` is a separate field rather than something an editor could type
    into link_url because link_url is a URLBlock — Django's URLValidator
    rejects a bare "#petition", so a same-page jump link had no way to be
    expressed at all before. It is the natural target for a hero CTA that
    scrolls to a signup/donate block further down the same page (see
    components/hero.html's banner CTA and each block's own anchor_id field).
    """

    text = CharBlock(label=_("Button text"))
    link_page = PageChooserBlock(
        required=False,
        label=_("Link page"),
        help_text=_("Internal page link. Set only one of the three link fields."),
    )
    link_url = URLBlock(
        required=False,
        label=_("Link URL"),
        help_text=_("External link. Set only one of the three link fields."),
    )
    anchor = CharBlock(
        required=False,
        label=_("Anchor"),
        help_text=_(
            "Jump to a block on this same page, by its Anchor ID and without "
            "the # symbol (e.g. 'petition'). Set only one of the three link "
            "fields."
        ),
    )
    style = ChoiceBlock(
        choices=BUTTON_STYLE_CHOICES,
        default="primary",
        label=_("Style"),
    )

    def clean(self, value):
        cleaned = super().clean(value)
        fields = ("link_page", "link_url", "anchor")
        set_count = sum(1 for name in fields if cleaned.get(name))
        errors = {}
        if set_count == 0:
            msg = ValidationError(
                _("Provide a link page, a link URL, or an anchor.")
            )
            errors = {name: msg for name in fields}
        elif set_count > 1:
            msg = ValidationError(
                _("Provide only one of link page, link URL, or anchor.")
            )
            errors = {name: msg for name in fields if cleaned.get(name)}
        if errors:
            raise StructBlockValidationError(block_errors=errors)
        return cleaned

    #: Centred in the pane, and laid out narrow so the preview scales the
    #: button *up*: at 1:1 a lone button is legible but lost in a pane this
    #: size. See templates/wagtailcore/shared/block_preview.html.
    preview_layout = "center"
    preview_target_width = 340

    class Meta:
        icon = "link"
        label = _("Button")
        template = "wtrx/components/streamfield/blocks/button_block.html"
        description = _(
            "A single call-to-action button. Links to a page on this site, an "
            "external URL, or an anchor further down the same page."
        )
        preview_value = {
            "text": _("Take action"),
            "link_url": "https://example.com",
            "style": "primary",
        }


BUTTON_GROUP_LAYOUT_CHOICES = [
    ("horizontal", _("Horizontal")),
    ("vertical", _("Vertical")),
]


class ButtonGroupBlock(StructBlock):
    """
    Two or more CTA buttons. Does not replace ButtonBlock (a single
    button) — that stays registered separately for pages that only need
    one CTA and for backward compatibility with existing content.

    `layout` picks between two arrangements:
      - "horizontal" (default): the same dynamic-centering row layout as
        CardGridBlock/ImageGridBlock/LogoGridBlock/PersonCardGridBlock —
        _balanced_rows() (max_per_row=3), rendered as centered flex rows.
        Buttons themselves size to their own content, unlike those other
        blocks' items — a button stretched to fill a row would look wrong.
      - "vertical": a single centered column, no row-balancing needed.

    NOTE: inline mid-paragraph buttons in rich text (a button embedded in
    the flow of a text block, like a styled link) were explicitly deferred
    — no custom Draftail entity/register_rich_text_features hook exists
    anywhere in this codebase, and building one is a materially bigger
    lift than this block. Revisit as a separate project if requested.
    """

    buttons = ListBlock(ButtonBlock(), min_num=1, max_num=5, label=_("Buttons"))
    layout = ChoiceBlock(
        choices=BUTTON_GROUP_LAYOUT_CHOICES,
        default="horizontal",
        label=_("Layout"),
        help_text=_(
            "Horizontal lays buttons out in centered rows. Vertical stacks "
            "them in a centered column."
        ),
    )

    MAX_PER_ROW = 3

    def get_context(self, value, parent_context=None):
        ctx = super().get_context(value, parent_context=parent_context)
        if value.get("layout") != "vertical":
            ctx["rows"] = _balanced_rows(value["buttons"], self.MAX_PER_ROW)
        return ctx

    class Meta:
        icon = "link"
        label = _("Button Group")
        template = "wtrx/components/streamfield/blocks/button_group_block.html"
        description = _(
            "Two or more call-to-action buttons, laid out horizontally or "
            "vertically. Use the single Button block instead for one CTA."
        )
        preview_value = {
            "buttons": [
                {
                    "text": _("Take action"),
                    "link_page": None,
                    "link_url": "https://example.com",
                    "anchor": "",
                    "style": "primary",
                },
                {
                    "text": _("Learn more"),
                    "link_page": None,
                    "link_url": "https://example.com",
                    "anchor": "",
                    "style": "outline",
                },
            ],
            "layout": "horizontal",
        }


_VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class _TagBalanceParser(HTMLParser):
    """
    Tracks open-tag nesting to catch the most common pasted-embed mistake
    (a stray or missing closing tag). Does not validate full HTML5
    conformance (attribute syntax etc.) — that would be noisy against
    legitimate third-party embed codes, which is exactly what RawHTMLBlock
    exists to hold. HTMLParser doesn't descend into <script>/<style>
    content as tags, so inline JS/CSS containing "<"/">" is not an issue.
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


def _html_is_balanced(value):
    parser = _TagBalanceParser()
    parser.feed(value)
    parser.close()
    return parser.is_balanced


class RawHTMLBlock(WagtailRawHTMLBlock):
    """
    A raw HTML passthrough block for embed codes, custom widgets, etc.

    Use sparingly. Output is not sanitized -- validation only checks tag
    balance (every opening tag has a matching closing tag), not markup
    safety. wagtail-localize will expose the raw markup to translators —
    brief editor guidance is recommended.
    """

    #: Laid out narrow so the preview scales it up: at the default desktop
    #: width this block's content is too small to read in the pane.
    preview_target_width = 700

    def clean(self, value):
        value = super().clean(value)
        if value and not _html_is_balanced(value):
            raise ValidationError(
                _(
                    "This HTML appears to have mismatched or unclosed tags "
                    "— check that every opening tag has a matching closing "
                    "tag."
                )
            )
        return value

    class Meta:
        icon = "code"
        label = _("Raw HTML")
        template = "wtrx/components/streamfield/blocks/raw_html_block.html"
        description = _(
            "Paste in HTML supplied by another service -- an embed, a widget, "
            "a snippet of markup. It is rendered exactly as given, so only use "
            "it for code you trust. Tag balance is validated on save; markup "
            "safety is not."
        )
        preview_value = (
            '<div style="border:2px dashed #9aa5a8;border-radius:8px;padding:24px;'
            'font-family:ui-monospace,monospace">'
            '<p style="margin:0 0 12px;font-weight:700">Embedded HTML</p>'
            '<p style="margin:0 0 16px">Markup you paste here renders as-is -- '
            'an embed, an iframe, or a widget from another service.</p>'
            '<code style="display:block;background:#eef1f2;padding:12px;'
            'border-radius:6px">&lt;iframe src="..."&gt;&lt;/iframe&gt;</code>'
            "</div>"
        )


class TableBlock(WagtailTableBlock):
    """
    A tabular data block using Wagtail's built-in table editor.
    """

    #: Same as RawHTMLBlock: table text is unreadable at the default width.
    preview_target_width = 800

    class Meta:
        icon = "table"
        label = _("Table")
        template = "wtrx/components/streamfield/blocks/table_block.html"
        description = _(
            "A simple data table, edited as a spreadsheet-style grid. The first "
            "row and column can each be marked as headers."
        )
        preview_value = {
            "first_row_is_table_header": True,
            "first_col_is_header": False,
            "table_caption": "",
            "data": [
                ["Region", "Coal plants retired", "Renewable capacity added"],
                ["Africa", "12", "4.1 GW"],
                ["Asia", "48", "31.7 GW"],
                ["Europe", "23", "18.2 GW"],
                ["Latin America", "9", "7.5 GW"],
            ],
        }


# ---------------------------------------------------------------------------
# Card blocks
# ---------------------------------------------------------------------------


class CardBlock(ContentPreviewMixin, StructBlock):
    """
    A content card with a heading, optional icon, optional image, description,
    and link.

    When an icon is set, it renders at 24x24 beside the content block. Used
    directly in the StreamField and as the child block of CardGridBlock. At
    most one of link_page or link_url may be set. clean() enforces this.

    `content` used to be two fields — `heading` (CharBlock, required) and
    `description` (a plain TextBlock, optional — no markup at all, unlike
    every other block condensed this way, whose body field was already
    richtext) — condensed into one richtext field, heading typed as an H3 to
    match the level card.html already rendered it at. Migration
    0051_condense_card_heading_description folded every existing card's
    heading/description pair into this field's HTML on upgrade, escaping and
    `<p>`-wrapping the plain-text description in the same step.
    """

    tag = CharBlock(
        required=False,
        label=_("Tag"),
        help_text=_("Optional short label displayed as a pill above the heading (e.g. 'Global')."),
    )
    icon = ImageChooserBlock(
        required=False,
        label=_("Icon"),
        help_text=_(
            "Optional small icon image (ideally square) displayed beside the content."
        ),
    )
    content = RichTextBlock(
        features=RICHTEXT_FEATURES_HEADING_H3,
        label=_("Content"),
        help_text=_("Type your heading as an H3 at the top, then optional supporting copy."),
    )
    image = ImageChooserBlock(
        required=False,
        label=_("Image"),
    )
    link_page = PageChooserBlock(
        required=False,
        label=_("Link page"),
        help_text=_("Internal link. Set either this or Link URL, not both."),
    )
    link_url = URLBlock(
        required=False,
        label=_("Link URL"),
        help_text=_("External link. Set either this or Link page, not both."),
    )
    link_text = CharBlock(
        required=False,
        default=_("Learn more"),
        label=_("Link text"),
        help_text=_("Label for the card's CTA button."),
    )

    def clean(self, value):
        cleaned = super().clean(value)
        errors = _validate_at_most_one_link(cleaned, {})
        if errors:
            raise StructBlockValidationError(block_errors=errors)
        return cleaned

    #: A card is never full width in practice -- it sits in a grid three to a
    #: row. Constrain the lone-card preview to the width one occupies there,
    #: so it matches what the Card Grid preview shows.
    preview_max_width = 400

    #: ...and lay that out in a narrower viewport than the 1280 default, which
    #: scales the card up to fill the pane instead of sitting small in the
    #: middle of it. Safe to do here only because card.html uses no responsive
    #: variants, so there are no breakpoints to lose.
    #:
    #: Height is what caps this, not width. A card is ~450px tall at 400px
    #: wide, and Wagtail gives the preview pane a 400px minimum height, so
    #: anything below ~790 here starts clipping the CTA off the bottom in a
    #: short pane.
    preview_target_width = 800

    class Meta:
        icon = "doc-full"
        label = _("Card")
        template = "wtrx/components/streamfield/blocks/card_block.html"
        description = _(
            "A single linked card: heading, short description, optional image, "
            "tag and icon. Usually reached for via Card Grid, which lays "
            "several out together."
        )


class CarouselCardBlock(CardBlock):
    """
    CardBlock variant used by CardCarouselBlock's `cards` ListBlock.

    Identical to CardBlock except image is required — every carousel card
    needs one, unlike the general-purpose CardBlock (used standalone and by
    CardGridBlock) where it's optional. Overriding just this one field, via
    subclassing rather than editing CardBlock directly, keeps every other
    use of CardBlock unchanged. No template of its own: rendered the same
    way as any other card, via components/card.html (see
    card_carousel_block.html).
    """

    image = ImageChooserBlock(
        label=_("Image"),
    )

    class Meta:
        icon = "doc-full"
        label = _("Card")


class PersonCardBlock(StructBlock):
    """
    A person or staff member card with name, role, photo, bio, and contact info.
    """

    name = CharBlock(label=_("Name"))
    role = CharBlock(
        required=False,
        label=_("Role / title"),
    )
    image = ImageChooserBlock(
        required=False,
        label=_("Photo"),
    )
    bio = WagtailTextBlock(
        required=False,
        label=_("Bio"),
    )
    email = EmailBlock(
        required=False,
        label=_("Email"),
    )
    phone = CharBlock(
        required=False,
        label=_("Phone"),
    )
    website = URLBlock(
        required=False,
        label=_("Website"),
    )

    #: A person card sits in a grid alongside others, never full width --
    #: same treatment as CardBlock, scaled up to fill the pane. It carries no
    #: image banner so it is shorter than a CardBlock and can be scaled further
    #: before the pane's 400px minimum height clips it.
    preview_max_width = 400
    preview_target_width = 640

    class Meta:
        icon = "user"
        label = _("Person")
        template = "wtrx/components/streamfield/blocks/person_card_block.html"
        description = _(
            "A person: photo, name, role and short bio, with optional contact "
            "details. Use for staff, spokespeople or board listings."
        )
        preview_value = staticmethod(_person_card_preview_value)


# ---------------------------------------------------------------------------
# Layout blocks
# ---------------------------------------------------------------------------


class AccordionItemBlock(StructBlock):
    """
    A single item in an AccordionBlock: a title and rich-text content.

    Explicitly named (not anonymous) so Django migration serialization can
    reference it by dotted path.

    This is an internal sub-block rendered by accordion_block.html — it is
    never rendered standalone via include_block and intentionally has
    no template in its Meta.
    """

    title = CharBlock(label=_("Title"))
    content = RichTextBlock(
        features=RICHTEXT_FEATURES_FULL,
        label=_("Content"),
    )

    class Meta:
        icon = "collapse-down"
        label = _("Accordion item")


class CardGridBlock(ContentPreviewMixin, StructBlock):
    """
    An auto-responsive grid of content cards.

    Minimum 2, maximum 12 cards. Same dynamic-centering layout as
    PersonCardGridBlock/ImageGridBlock/LogoGridBlock (`_balanced_rows()`,
    max_per_row=3, defined further down this file before
    ImageGridBlock — Python doesn't care about definition order across a
    module for a call inside a method body, only that the name exists by
    the time the method actually runs). No column-count controls — editors
    cannot break the layout.

    This replaced an earlier CSS-only special case (2 or 4 cards get
    lg:grid-cols-2, everything else lg:grid-cols-3) that only handled one
    bad count: 7 cards under that scheme rendered as an unbalanced 3+3+1,
    the exact orphan-row bug PersonCardGridBlock was built to avoid.
    `_balanced_rows()` fixes every count, not just 4.

    heading is optional (blank renders nothing above the grid), same
    required=False pattern as PageCardsBlock.heading — for consistency with
    the other section-heading-plus-cards blocks (CardCarouselBlock,
    PageCardsBlock), not because CardGridBlock's own layout needs it.
    """

    heading = CharBlock(
        required=False,
        label=_("Heading"),
        help_text=_("Section heading, rendered as an H2."),
    )
    cards = ListBlock(
        CardBlock(),
        min_num=2,
        max_num=12,
        label=_("Cards"),
    )

    MAX_PER_ROW = 3

    #: 5 demonstrates the 3+2 balanced-row case in the block picker preview.
    preview_max_items = {"cards": 5}

    def get_context(self, value, parent_context=None):
        ctx = super().get_context(value, parent_context=parent_context)
        ctx["rows"] = _balanced_rows(value["cards"], self.MAX_PER_ROW)
        return ctx

    class Meta:
        icon = "grip"
        label = _("Card Grid")
        template = "wtrx/components/streamfield/blocks/card_grid_block.html"
        description = _(
            "An auto-responsive grid of 2-12 linked cards, laid out "
            "automatically — never a lone card on its own row. There are no "
            "column controls."
        )


class ImageGridItemBlock(StructBlock):
    """
    A single item in an ImageGridBlock's `images` list: just an image and
    an optional alt-text override. This is an internal sub-block rendered
    by image_grid_block.html — no Meta.template, same as
    ImageCardListItemBlock.
    """

    image = ImageChooserBlock(label=_("Image"))
    alt_text = CharBlock(
        required=False,
        label=_("Alt text"),
        help_text=_(
            "Overrides the image description for screen readers. Leave "
            "blank to use the description set on the image itself."
        ),
    )

    class Meta:
        icon = "image"
        label = _("Image")


def _balanced_rows(items, max_per_row):
    """
    Split `items` into rows of `max_per_row` (preferred) and
    `max_per_row - 1`, larger rows first, so a partial trailing row is
    never a lone item of 1 — the same dynamic-centering technique used by
    CardGridBlock's spirit (auto layout, no editor column control) but
    generalized to genuinely avoid an orphan row for *every* count, not
    just one special-cased count.

    A single global row size (uniformly `k` or `k - 1` for every row)
    cannot avoid a trailing row of exactly 1 for every possible count —
    see PersonCardGridBlock's original derivation for `max_per_row == 3`,
    proven in AGENTS.md pitfall #44. The general fix: choose the minimum
    row count `R = ceil(n / max_per_row)` needed to respect the cap, then
    distribute `n` items across those `R` rows as evenly as possible
    (`divmod(n, R)`), rather than always preferring the biggest row size.
    This provably keeps every row at 2+ items whenever `n > max_per_row`
    and `max_per_row >= 3` (see TestBalancedRows for the property test).
    `n <= max_per_row` is simply one centered row of everything.
    """
    # Wagtail's ListValue.__getitem__ only handles integer indices, not
    # slice objects (items[i:j] silently misbehaves rather than raising),
    # so convert to a plain list up front.
    items = list(items)
    n = len(items)
    if n <= max_per_row:
        return [items]
    rows_count = math.ceil(n / max_per_row)
    base, extra = divmod(n, rows_count)
    sizes = [base + 1] * extra + [base] * (rows_count - extra)
    rows, i = [], 0
    for size in sizes:
        rows.append(items[i : i + size])
        i += size
    return rows


class ImageGridBlock(StructBlock):
    """
    An auto-responsive grid of photos, laid out with the same dynamic
    centering as PersonCardGridBlock (via `_balanced_rows()`, capped at 4
    per row) rather than CardGridBlock's fixed-breakpoint CSS grid — no
    count ever leaves a lone photo on its own row, and a small photo count
    centers as one row instead of stretching thin across the full width.
    No per-image caption field — this is a grid, not a set of
    individually captioned figures.

    Not ContentPreviewMixin: no real page uses this block yet, so there is
    nothing to harvest -- see _image_grid_preview_value().
    """

    heading = CharBlock(
        required=False,
        label=_("Heading"),
        help_text=_("Section heading, rendered as an H2."),
    )
    images = ListBlock(
        ImageGridItemBlock(),
        min_num=2,
        max_num=24,
        label=_("Images"),
    )

    #: Photos are larger than logos, so a lower per-row cap than
    #: LogoGridBlock's -- see _balanced_rows().
    MAX_PER_ROW = 4

    def get_context(self, value, parent_context=None):
        ctx = super().get_context(value, parent_context=parent_context)
        ctx["rows"] = _balanced_rows(value["images"], self.MAX_PER_ROW)
        return ctx

    class Meta:
        icon = "grip"
        label = _("Image Grid")
        template = "wtrx/components/streamfield/blocks/image_grid_block.html"
        description = _(
            "An auto-responsive grid of 2-24 photos, cropped to a consistent "
            "square shape. No per-image captions. There are no column controls."
        )
        preview_value = staticmethod(_image_grid_preview_value)


class LogoGridItemBlock(StructBlock):
    """
    A single item in a LogoGridBlock's `logos` list: an image, an
    organization name (used as the alt-text fallback and, if the logo
    links out, its accessible label), and an optional link.
    """

    image = ImageChooserBlock(label=_("Logo"))
    name = CharBlock(
        label=_("Organization name"),
        help_text=_(
            "Used as alt text if the image has no description, and as the "
            "logo's accessible label if it links out."
        ),
    )
    link_page = PageChooserBlock(
        required=False,
        label=_("Link page"),
        help_text=_("Internal page link. Set only one of the two link fields."),
    )
    link_url = URLBlock(
        required=False,
        label=_("Link URL"),
        help_text=_("External link. Set only one of the two link fields."),
    )

    def clean(self, value):
        cleaned = super().clean(value)
        errors = _validate_at_most_one_link(cleaned, {})
        if errors:
            raise StructBlockValidationError(block_errors=errors)
        return cleaned

    class Meta:
        icon = "site"
        label = _("Logo")


class LogoGridBlock(StructBlock):
    """
    A grid of partner/funder logos, sized consistently regardless of each
    logo's own aspect ratio (a fixed-height cell, object-contain). Same
    dynamic-centering layout as ImageGridBlock/PersonCardGridBlock (via
    `_balanced_rows()`), capped denser at 5 per row since logos are small
    marks rather than photos. Logos may optionally link out.

    Not ContentPreviewMixin: no real page uses this block yet, so there is
    nothing to harvest -- see _logo_grid_preview_value().
    """

    heading = CharBlock(required=False, label=_("Heading"))
    logos = ListBlock(
        LogoGridItemBlock(),
        min_num=2,
        max_num=30,
        label=_("Logos"),
    )

    #: Denser than ImageGridBlock's cap -- logos are small marks, not
    #: photos -- see _balanced_rows().
    MAX_PER_ROW = 5

    def get_context(self, value, parent_context=None):
        ctx = super().get_context(value, parent_context=parent_context)
        ctx["rows"] = _balanced_rows(value["logos"], self.MAX_PER_ROW)
        return ctx

    class Meta:
        icon = "grip"
        label = _("Logo Grid")
        template = "wtrx/components/streamfield/blocks/logo_grid_block.html"
        description = _(
            "A grid of 2-30 partner/funder logos, sized consistently. Logos "
            "may optionally link out."
        )
        preview_value = staticmethod(_logo_grid_preview_value)


class PersonCardGridBlock(StructBlock):
    """
    A grid of people (staff, spokespeople, board members), laid out so
    there is never a lone card on its own row — see _balanced_rows(),
    called here with max_per_row=3.

    Flexbox with justify-center, not CSS Grid like CardGridBlock: rows are
    computed explicitly in Python and each renders as its own small flex
    row, so a partial row (e.g. 2 people) centers naturally. Reuses
    PersonCardBlock as the item block and person_card.html for per-item
    rendering — the standalone `person_card` registration is unchanged,
    for single-person spotlight use. ImageGridBlock and LogoGridBlock use
    the same technique (same _balanced_rows() helper, their own caps).

    Not ContentPreviewMixin: no real page uses this block yet, so there is
    nothing to harvest -- see _person_card_grid_preview_value(). 5 people
    in that preview demonstrates the 3+2 row split.
    """

    heading = CharBlock(required=False, label=_("Heading"))
    people = ListBlock(
        PersonCardBlock(),
        min_num=1,
        max_num=12,
        label=_("People"),
    )

    MAX_PER_ROW = 3

    def get_context(self, value, parent_context=None):
        ctx = super().get_context(value, parent_context=parent_context)
        ctx["rows"] = _balanced_rows(value["people"], self.MAX_PER_ROW)
        return ctx

    class Meta:
        icon = "group"
        label = _("Person Card Grid")
        template = "wtrx/components/streamfield/blocks/person_card_grid_block.html"
        description = _(
            "A grid of up to 12 people, laid out automatically — never a "
            "lone card on its own row. There are no column controls."
        )
        preview_value = staticmethod(_person_card_grid_preview_value)


class ImageCardListItemBlock(StructBlock):
    """
    A single item in an ImageCardListBlock's `cards` list: a heading and a
    description, nothing else — no icon/image/link, unlike CardBlock. This
    layout's cards are plain bordered text boxes (see image_card_list_block.html),
    so reusing CardBlock would expose fields the template never renders.

    `content` used to be two fields — `heading` (CharBlock) and `description`
    (a plain TextBlock, no markup) — condensed into one richtext field, same
    treatment and same reasoning as CardBlock's own merge (heading typed as
    an H3, matching the level this template already rendered it at).
    Migration 0051_condense_card_heading_description folded every existing
    item's heading/description pair into this field's HTML on upgrade.
    """

    content = RichTextBlock(
        features=RICHTEXT_FEATURES_HEADING_H3,
        label=_("Content"),
        help_text=_("Type your heading as an H3 at the top, then the supporting copy."),
    )

    class Meta:
        icon = "doc-full"
        label = _("Card")


class ImageCardListBlock(ContentPreviewMixin, StructBlock):
    """
    A centered heading above a two-column split: an image on the left, a
    vertical stack of simple text cards (ImageCardListItemBlock) on the
    right. Both columns share the same height (image is object-cover'd to
    match), single column on mobile — see image_card_list_block.html.

    Full-bleed-ish width: special-cased in content_page.html/home_page.html
    to skip the shared max-w-5xl wrapper, same width (max-w-7xl / 1280px) as
    CalloutBlock — see that block's template comment for the two-tier
    w-full-outer / max-w-inner pattern this reuses.
    """

    heading = CharBlock(
        label=_("Heading"),
        help_text=_("Centered heading above the image and cards."),
    )
    image = ImageChooserBlock(label=_("Image"))
    cards = ListBlock(
        ImageCardListItemBlock(),
        min_num=2,
        label=_("Cards"),
    )
    alignment = ChoiceBlock(
        choices=IMAGE_ALIGNMENT_CHOICES,
        default="image-left",
        label=_("Image alignment"),
        help_text=_("Which side the image sits on — the cards sit on the opposite side."),
    )

    class Meta:
        icon = "grip"
        label = _("Image Card List")
        template = "wtrx/components/streamfield/blocks/image_card_list_block.html"


class ImageTextBlock(ContentPreviewMixin, StructBlock):
    """
    A two-column split: an image on the left (natural aspect ratio, not
    stretched to match the text column like ImageCardListBlock's image
    does), a heading + richtext body on the right. Both columns are
    top-aligned, single column on mobile — see image_text_block.html.

    Distinct from ImageCardListBlock: that one has a heading spanning
    above both columns and a fixed list of bordered cards; this one has no
    top heading at all — its heading sits inline in the text column — and
    the "cards" are just one richtext field, for freeform paragraph copy
    (e.g. a campaign pitch) rather than a repeatable list of short points.

    `content` used to be two fields — `heading` (CharBlock) and `text`
    (RichTextBlock) — condensed into this one richtext field so the editor
    types the heading as an H2 at the top, the same convention SectionBlock's
    own content list already uses. Migration 0045_condense_heading_text_blocks
    folded every existing page's heading/text pair into this field's HTML on
    upgrade; see that migration for the exact transform.
    """

    image = ImageChooserBlock(label=_("Image"))
    content = RichTextBlock(
        features=RICHTEXT_FEATURES_HEADING_H2,
        label=_("Content"),
        help_text=_("Type your heading as an H2 at the top, then the body text."),
    )
    alignment = ChoiceBlock(
        choices=IMAGE_ALIGNMENT_CHOICES,
        default="image-left",
        label=_("Image alignment"),
        help_text=_("Which side the image sits on — the text sits on the opposite side."),
    )

    class Meta:
        icon = "image"
        label = _("Image + Text")
        template = "wtrx/components/streamfield/blocks/image_text_block.html"


class FeaturePanelBlock(ContentPreviewMixin, StructBlock):
    """
    A filled, rounded panel holding an image beside a text stack: optional
    eyebrow pill, heading, optional body copy, optional CTA button with a
    trailing arrow. Image side (left/right) and background (light/dark) are
    both editor choices — see feature_panel_block.html.

    Per Figma's Take Action page (node 1:1021), this is the block used both
    above the card grid ("Featured Campaign" / light panel with a pill) and
    below it ("Looking for more?" / dark panel without one). They are one
    component with two configurations, not two blocks.

    Distinct from ImageTextBlock: that block has no panel at all — image and
    text sit directly on the page background, top-aligned, with no eyebrow
    and no CTA. This one is a self-contained card with its own fill, border
    radius and internal padding, and its columns are vertically centered
    against each other.

    Distinct from CalloutBlock: that block is text-only on a solid color
    (any background image is a faint full-bleed watermark, not a subject);
    this one gives the image its own column at full opacity.

    At most one of link_page, link_url or anchor may be set; clean()
    enforces this, same pattern as CardBlock and QuoteBlock. `anchor` exists
    for the same reason it does on ButtonBlock — link_url is a URLBlock and
    Django's URLValidator rejects a bare "#petition", so a panel whose CTA
    scrolls to a signup block further down the same page had no way to
    express that target at all.

    `content` used to be two fields — `heading` (CharBlock) and `text`
    (optional RichTextBlock) — condensed into this one richtext field so the
    editor types the heading as an H2 at the top, same as ImageTextBlock.
    `eyebrow` stays a separate field: it renders as its own pill, not part of
    the text flow. Migration 0045_condense_heading_text_blocks folded every
    existing page's heading/text pair into this field's HTML on upgrade.
    """

    eyebrow = CharBlock(
        required=False,
        label=_("Eyebrow"),
        help_text=_(
            "Optional short label shown in a pill above the heading, "
            'e.g. "Featured Campaign". Leave blank to omit the pill.'
        ),
    )
    content = RichTextBlock(
        features=RICHTEXT_FEATURES_HEADING_H2,
        label=_("Content"),
        help_text=_("Type your heading as an H2 at the top, then optional supporting copy."),
    )
    image = ImageChooserBlock(label=_("Image"))
    alignment = ChoiceBlock(
        choices=IMAGE_ALIGNMENT_CHOICES,
        default="image-left",
        label=_("Alignment"),
        help_text=_("Which side of the panel the image sits on."),
    )
    background = ChoiceBlock(
        choices=BACKGROUND_COLOR_CHOICES,
        default="white",
        label=_("Background"),
        help_text=_(
            "Panel fill. The dark colors invert the text, pill and button "
            "colors; White and Light grey keep them dark."
        ),
    )
    link_text = CharBlock(
        required=False,
        label=_("Button text"),
        help_text=_("Optional CTA button label. Leave blank to omit the button."),
    )
    link_page = PageChooserBlock(
        required=False,
        label=_("Link page"),
        help_text=_("Internal link. Set either this or Link URL, not both."),
    )
    link_url = URLBlock(
        required=False,
        label=_("Link URL"),
        help_text=_("External link. Set only one of the three link fields."),
    )
    anchor = CharBlock(
        required=False,
        label=_("Anchor"),
        help_text=_(
            "Jump to a block on this same page, by its Anchor ID and without "
            "the # symbol (e.g. 'petition'). Set only one of the three link "
            "fields."
        ),
    )

    def clean(self, value):
        cleaned = super().clean(value)
        errors = _validate_at_most_one_link(cleaned, {}, extra_fields=("anchor",))
        if errors:
            raise StructBlockValidationError(block_errors=errors)
        return cleaned

    class Meta:
        icon = "image"
        label = _("Feature Panel")
        template = "wtrx/components/streamfield/blocks/feature_panel_block.html"


class CardCarouselBlock(ContentPreviewMixin, StructBlock):
    """
    A heading + supporting copy, an optional CTA button, and a horizontally
    scrollable row of cards with prev/next arrow controls.

    Cards are manually authored (a ListBlock of CarouselCardBlock, not
    pulled from pages) — minimum 3, no maximum. At most one of link_page or
    link_url may be set; clean() enforces this, same pattern as CardBlock
    and QuoteBlock.

    `content` used to be two fields — `heading` (CharBlock) and `content`
    (RichTextBlock) — condensed into this one richtext field, same
    convention as ImageTextBlock/FeaturePanelBlock: the editor types the
    heading as an H2 at the top, then the supporting copy. Migration
    0045_condense_heading_text_blocks folded every existing page's
    heading/content pair into this field's HTML on upgrade.
    """

    content = RichTextBlock(
        features=RICHTEXT_FEATURES_HEADING_H2,
        label=_("Content"),
        help_text=_("Type your heading as an H2 at the top, then the supporting copy."),
    )
    link_text = CharBlock(
        required=False,
        label=_("Button text"),
        help_text=_("Optional CTA button label. Leave blank to omit the button."),
    )
    link_page = PageChooserBlock(
        required=False,
        label=_("Link page"),
        help_text=_("Internal link. Set either this or Link URL, not both."),
    )
    link_url = URLBlock(
        required=False,
        label=_("Link URL"),
        help_text=_("External link. Set either this or Link page, not both."),
    )
    cards = ListBlock(
        CarouselCardBlock(),
        min_num=3,
        label=_("Cards"),
    )

    def clean(self, value):
        cleaned = super().clean(value)
        errors = _validate_at_most_one_link(cleaned, {})
        if errors:
            raise StructBlockValidationError(block_errors=errors)
        return cleaned

    class Meta:
        icon = "grip"
        label = _("Card Carousel")
        template = "wtrx/components/streamfield/blocks/card_carousel_block.html"


class PageCardsBlock(ContentPreviewMixin, StructBlock):
    """
    A heading + optional subheading, and a row of cards auto-generated from
    the most recently published child pages of a chosen index page, plus an
    optional CTA button linking to that index page.

    Unlike CardCarouselBlock, cards aren't manually authored — they're the 3
    most recently published live/public children of index_page (same
    get_children().live().public().specific() query IndexPage.get_context()
    uses), converted to card dicts via the same page_as_card() tag
    index_page.html uses, so this always reflects whatever's actually
    published there.

    Ordering follows whatever the chosen index page itself uses for its
    listing. A Blogs page (blog posts and press releases) exposes that as
    get_listing_queryset(), ordering by the editor-controlled published_at
    — the same date the cards display — so a "Latest updates" row can't
    disagree with the index it links to about which posts are newest. This
    matters because Wagtail only sets first_published_at when a page is
    published through the admin, so imported posts all carry NULL or an
    import-time value there (see the backfill_first_published command).

    A generic IndexPage has no such method and may mix child page types, so
    it falls back to first_published_at, which every Page has — keeping
    that case a single query. The date shown on each card still prefers
    published_at whenever the child has one.

    `content` used to be two fields — `heading` (CharBlock) and `subheading`
    (RichTextBlock, rendered as a plain paragraph despite its name, not an
    H3) — condensed into this one richtext field, same convention as
    ImageTextBlock: the editor types the heading as an H2 at the top, then
    the supporting copy. Migration 0047_condense_more_heading_text_blocks
    folded every existing page's heading/subheading pair into this field's
    HTML on upgrade.
    """

    content = RichTextBlock(
        features=RICHTEXT_FEATURES_HEADING_H2,
        required=False,
        label=_("Content"),
        help_text=_("Type your heading as an H2 at the top, then optional supporting copy."),
    )
    index_page = PageChooserBlock(
        page_type=["wtrx.IndexPage", "wtrx.Blogs"],
        label=_("Index page"),
        help_text=_(
            "The 3 most recently published pages under this index page are shown as cards."
        ),
    )
    link_text = CharBlock(
        required=False,
        default=_("Read more"),
        label=_("Button text"),
        help_text=_(
            "Optional CTA button below the cards. Always links to the index page above."
        ),
    )

    def get_context(self, value, parent_context=None):
        from wtrx.templatetags.wtrx_tags import page_as_card

        context = super().get_context(value, parent_context=parent_context)
        index_page = value.get("index_page")
        cards = []
        if index_page is not None:
            specific_index = index_page.specific
            listing = getattr(specific_index, "get_listing_queryset", None)
            if listing is not None:
                children = listing()[:3]
            else:
                children = (
                    specific_index.get_children()
                    .live()
                    .public()
                    .specific()
                    .order_by("-first_published_at")[:3]
                )
            for child in children:
                card = page_as_card(child)
                card["date"] = getattr(child, "published_at", None) or child.first_published_at
                cards.append(card)
        context["cards"] = cards
        return context

    class Meta:
        icon = "grip"
        label = _("Page Cards")
        template = "wtrx/components/streamfield/blocks/page_cards_block.html"


class AccordionBlock(ContentPreviewMixin, StructBlock):
    """
    A collapsible accordion (FAQ-style) list.

    Minimum 1 item. No heading field — editors use a TextBlock h2 before
    this block if a heading is needed.
    """

    items = ListBlock(
        AccordionItemBlock(),
        min_num=1,
        label=_("Items"),
    )

    class Meta:
        icon = "list-ul"
        label = _("Accordion")
        template = "wtrx/components/streamfield/blocks/accordion_block.html"


def _quote_preview_value():
    """
    Placeholder value for QuoteBlock's picker preview.

    A function rather than a dict literal because it needs a real image from
    the database, which must not be read at import time. Assigned to
    `Meta.preview_value` via staticmethod() -- Wagtail instantiates the Meta
    class, so a plain function there would be bound and called with `self`.
    """
    return {
        "content": "<p>A short, punchy line lifted from the page and given room to breathe.</p>",
        "image": preview_image(),
        "link_text": _("Read the full story"),
        "link_url": "https://example.com",
        "alignment": "image-left",
    }


class QuoteBlock(StructBlock):
    """
    An image or video with highlighted (pull-quote-style) text overlaid on it.

    The media renders at ~80% width; alignment (image-left / image-right)
    controls which side it sits on, with the text on the opposite side.
    Optional CTA button link.

    Exactly one of image or media_file must be set; clean() enforces this.
    At most one of link_page or link_url may be set; clean() enforces this.

    Replaces an earlier, unrelated plain pull-quote block (quote text +
    attribution, no image) that also used the "Quote" name/block key —
    that one is gone, not renamed alongside this; this is the image-overlay
    design becoming "Quote", nothing about it changed for the rename.
    """

    content = RichTextBlock(
        features=RICHTEXT_FEATURES_FULL,
        label=_("Content"),
    )
    image = ImageChooserBlock(
        required=False,
        label=_("Image"),
        help_text=_("Set either this or Media file, not both."),
    )
    media_file = VideoChooserBlock(
        required=False,
        label=_("Media file"),
        help_text=_(
            "An uploaded video file from the media library. Set either this or Image, not both."
        ),
    )
    link_text = CharBlock(
        required=False,
        label=_("Link text"),
        help_text=_("CTA button label. Leave blank to omit the button."),
    )
    link_page = PageChooserBlock(
        required=False,
        label=_("Link page"),
        help_text=_("Internal link. Set either this or Link URL, not both."),
    )
    link_url = URLBlock(
        required=False,
        label=_("Link URL"),
        help_text=_("External link. Set either this or Link page, not both."),
    )
    alignment = ChoiceBlock(
        choices=IMAGE_ALIGNMENT_CHOICES,
        default="image-left",
        label=_("Media alignment"),
        help_text=_(
            "Which side the (~80%-width) image sits on — the text sits on "
            "the opposite side."
        ),
    )

    def clean(self, value):
        cleaned = super().clean(value)
        errors = {}
        has_image = bool(cleaned.get("image"))
        has_video = bool(cleaned.get("media_file"))
        if not has_image and not has_video:
            msg = ValidationError(_("Provide either an image or a media file."))
            errors["image"] = msg
            errors["media_file"] = msg
        elif has_image and has_video:
            msg = ValidationError(
                _("Provide either an image or a media file, not both.")
            )
            errors["image"] = msg
            errors["media_file"] = msg
        errors = _validate_at_most_one_link(cleaned, errors)
        if errors:
            raise StructBlockValidationError(block_errors=errors)
        return cleaned

    class Meta:
        icon = "image"
        label = _("Quote")
        template = "wtrx/components/streamfield/blocks/quote_block.html"
        description = _(
            "A large pull-quote set beside an image or video, with an optional "
            "button. Best used once on a page, for a testimonial or key line."
        )
        preview_value = staticmethod(_quote_preview_value)


class CalloutBlock(ContentPreviewMixin, StructBlock):
    """
    A solid-color card: optional heading, optional subheading,
    optional paragraph, optional CTA button, and an optional low-opacity
    background image (a subtle texture/watermark behind the text, not a
    full photo — see callout_block.html).

    Text/button color (light vs dark) is derived from the chosen color, not
    independently editable — navy/red/dark-grey/blue-gradient are all dark
    enough to need light (white) text and a light-outline button; white and
    light-grey need dark text and a dark-outline button. See
    LIGHT_BACKGROUND_COLORS and main.css's .wtr-bg-{color} classes for that
    pairing.

    `content` used to be three fields — `heading` (H2), `subheading` (H3) and
    `content` (paragraph) — condensed into this one richtext field, all
    optional (a callout can be just a background + button). The editor types
    an H2 and/or H3 at the top followed by the paragraph, same convention as
    ImageTextBlock/FeaturePanelBlock. Migration
    0045_condense_heading_text_blocks folded every existing page's
    heading/subheading/content trio into this field's HTML on upgrade.
    """

    content = RichTextBlock(
        features=RICHTEXT_FEATURES_HEADINGS_H2_H3,
        required=False,
        label=_("Content"),
        help_text=_(
            "Optional heading (H2) and/or subheading (H3) at the top, "
            "followed by an optional paragraph."
        ),
    )
    link_text = CharBlock(
        required=False,
        label=_("Link text"),
        help_text=_("CTA button label. Leave blank to omit the button."),
    )
    link_page = PageChooserBlock(
        required=False,
        label=_("Link page"),
        help_text=_("Internal link. Set either this or Link URL, not both."),
    )
    link_url = URLBlock(
        required=False,
        label=_("Link URL"),
        help_text=_("External link. Set either this or Link page, not both."),
    )
    color = ChoiceBlock(
        choices=BACKGROUND_COLOR_CHOICES,
        default="navy",
        label=_("Color"),
    )
    image = ImageChooserBlock(
        required=False,
        label=_("Background image"),
        help_text=_(
            "Optional. Rendered as a subtle, low-opacity texture behind the "
            "text — not a full photo background."
        ),
    )

    def clean(self, value):
        cleaned = super().clean(value)
        errors = _validate_at_most_one_link(cleaned, {})
        if errors:
            raise StructBlockValidationError(block_errors=errors)
        return cleaned

    class Meta:
        icon = "pick"
        label = _("Callout")
        template = "wtrx/components/streamfield/blocks/callout_block.html"
        description = _(
            "A solid-colour panel with a heading and a call-to-action button. "
            "Use it to break up a long page and push readers toward one action."
        )


# ---------------------------------------------------------------------------
# Action blocks
#
# SectionBlock is defined after this section since its `content` field needs
# to instantiate DonateBlock and SignupActionNetworkBlock.
# ---------------------------------------------------------------------------


class DonateBlock(StructBlock):
    """
    A donation call-to-action section.

    Behavior (platform, base URL, suggested amounts) is driven by
    IntegrationSettings at render time — not hardcoded here. The
    override_amounts and override_url fields let editors override the
    site-wide defaults on a per-block basis.

    `content` used to be two fields — `heading` (CharBlock) and
    `description` (RichTextBlock), both optional — condensed into this one
    richtext field, same convention as ImageTextBlock. Migration
    0047_condense_more_heading_text_blocks folded every existing page's
    heading/description pair into this field's HTML on upgrade.
    """

    content = RichTextBlock(
        features=RICHTEXT_FEATURES_HEADING_H2,
        required=False,
        label=_("Content"),
        help_text=_("Type your heading as an H2 at the top, then optional supporting copy."),
    )
    button_text = CharBlock(
        required=False,
        default=_("Donate"),
        label=_("Button text"),
        help_text=_("Leave blank to use the site default button label."),
    )
    override_amounts = ListBlock(
        DecimalBlock(min_value=Decimal("0.01"), decimal_places=2),
        required=False,
        label=_("Override amounts"),
        help_text=_(
            "Optional list of suggested donation amounts. "
            "Leave empty to use the site-wide defaults."
        ),
    )
    override_url = URLBlock(
        required=False,
        label=_("Override URL"),
        help_text=_(
            "Optional override for the donation URL. "
            "Overrides the site-wide donation base URL from IntegrationSettings."
        ),
    )

    def get_context(self, value, parent_context=None):
        ctx = super().get_context(value, parent_context=parent_context)
        request = (parent_context or {}).get("request")
        actblue_config = None
        if request is not None:
            try:
                actblue_config = IntegrationSettings.for_request(request).get_integration_config(
                    "actblue"
                )
            except (IntegrationSettings.DoesNotExist, Site.DoesNotExist):
                actblue_config = None

        ctx["donation_base_url"] = actblue_config.get("base_url") if actblue_config else ""
        suggested_amounts = actblue_config.get("suggested_amounts") if actblue_config else ""
        if suggested_amounts:
            try:
                ctx["donation_suggested_amounts_list"] = [
                    Decimal(x.strip()) for x in suggested_amounts.split(",") if x.strip()
                ]
            except (InvalidOperation, AttributeError):
                ctx["donation_suggested_amounts_list"] = []
        else:
            ctx["donation_suggested_amounts_list"] = []
        return ctx

    class Meta:
        icon = "pick"
        label = _("Donate")
        template = "wtrx/components/streamfield/blocks/donate_block.html"
        description = _(
            "A donation ask with suggested amounts, linking out to ActBlue. "
            "Amounts and the destination come from Settings > Integrations "
            "unless overridden here."
        )
        preview_value = {
            "content": (
                "<h2>Chip in to keep the pressure on</h2>"
                "<p>Every contribution funds organisers, research and public campaigning.</p>"
            ),
            "button_text": _("Donate"),
            "override_amounts": ["10", "25", "50", "100"],
            "override_url": "https://example.com/donate",
        }


class DonateFundraiseUpBlock(ContentPreviewMixin, StructBlock):
    """
    A Fundraise Up donate button.

    Fundraise Up elements (buttons, forms, overlays) are created in Fundraise
    Up's own dashboard, each yielding an opaque Element ID. Embedding one is
    just a hidden anchor tag that Fundraise Up's installation script (loaded
    site-wide via IntegrationSettings.head_html() when the Fundraise Up
    integration is enabled) scans for and hydrates into a styled checkout-modal
    trigger. The button's appearance and label are configured in the Fundraise
    Up dashboard for that element, not here — unlike DonateBlock, there is no
    button_text field.

    Renders as a photo beside a dark panel (heading, description, the
    Fundraise Up element) — use a Fundraise Up element configured as an
    inline/embedded form in your dashboard, not a modal-trigger button, so
    it actually renders inline in the panel rather than as a small button.

    `content` used to be two fields — `heading` (CharBlock) and
    `description` (RichTextBlock), both optional — condensed into this one
    richtext field, same convention as ImageTextBlock. Migration
    0047_condense_more_heading_text_blocks folded every existing page's
    heading/description pair into this field's HTML on upgrade.

    There is deliberately no `element_id` field on this block any more — every
    instance always shows the visitor's region-specific Fundraise Up element,
    resolved client-side from FundraiseUpConfigBlock's settings (see
    wtrx/integrations/fundraiseup.py for the full geolocation mechanism and
    why it has to be client-side on this cached site). A block author who
    wants a single fixed element regardless of region has no override here —
    that was a deliberate product decision, not an oversight.
    """

    content = RichTextBlock(
        features=RICHTEXT_FEATURES_HEADING_H2,
        required=False,
        label=_("Content"),
        help_text=_("Type your heading as an H2 at the top, then optional supporting copy."),
    )
    image = ImageChooserBlock(
        required=False,
        label=_("Image"),
    )
    image_caption = CharBlock(
        required=False,
        label=_("Image caption"),
        help_text=_("Optional caption overlaid on the image, e.g. a photo credit."),
    )
    designation_id = CharBlock(
        required=False,
        label=_("Designation ID"),
        help_text=_(
            "Optional Fundraise Up designation ID to route this donation to "
            "a specific fund. Applies on top of whichever region-specific "
            "form the visitor is shown."
        ),
    )
    alignment = ChoiceBlock(
        choices=IMAGE_ALIGNMENT_CHOICES,
        default="image-left",
        label=_("Image alignment"),
        help_text=_(
            "Which side the image sits on — the dark panel sits on the "
            "opposite side. Has no effect when no image is set."
        ),
    )

    def get_context(self, value, parent_context=None):
        ctx = super().get_context(value, parent_context=parent_context)
        request = (parent_context or {}).get("request")
        fundraiseup_config = None
        if request is not None:
            try:
                fundraiseup_config = IntegrationSettings.for_request(request).get_integration_config(
                    "fundraiseup"
                )
            except (IntegrationSettings.DoesNotExist, Site.DoesNotExist):
                fundraiseup_config = None

        default_id = fundraiseup_config.get("element_id_default", "") if fundraiseup_config else ""
        ctx["fundraiseup_default_element_id"] = default_id

        if fundraiseup_config:
            eu_codes_raw = fundraiseup_config.get("eu_country_codes", "") or ""
            eu_codes = [code.strip().upper() for code in eu_codes_raw.split(",") if code.strip()]
            # Every region falls back to the site default when its own field
            # is left blank, rather than resolving to an empty element ID —
            # an editor who's only filled in a couple of regions still gets a
            # working donate form for everyone else.
            ctx["fundraiseup_region_map_json"] = json.dumps(
                {
                    "US": fundraiseup_config.get("element_id_us", "") or default_id,
                    "NL": fundraiseup_config.get("element_id_nl", "") or default_id,
                    "CA": fundraiseup_config.get("element_id_ca", "") or default_id,
                    "GB": fundraiseup_config.get("element_id_gb", "") or default_id,
                    "_eu": fundraiseup_config.get("element_id_eu", "") or default_id,
                    "_eu_countries": eu_codes,
                    "_default": default_id,
                }
            )
        else:
            ctx["fundraiseup_region_map_json"] = json.dumps({"_default": ""})
        return ctx

    class Meta:
        icon = "pick"
        label = _("Donate (Fundraise Up)")
        template = "wtrx/components/streamfield/blocks/donate_fundraiseup_block.html"


class SignupWagtailFormsBlock(StructBlock):
    """
    Renders a Wagtail FormPage's form inline.

    AJAX submission posts to form_page.url. On success, the form is replaced
    with success_message (or a generic fallback). The form instance is
    instantiated in the template via form_page.get_form_class()().

    `content` used to be two fields — `heading` (CharBlock) and
    `description` (RichTextBlock), both optional — condensed into this one
    richtext field, same convention as ImageTextBlock. Migration
    0047_condense_more_heading_text_blocks folded every existing page's
    heading/description pair into this field's HTML on upgrade.
    """

    content = RichTextBlock(
        features=RICHTEXT_FEATURES_HEADING_H2,
        required=False,
        label=_("Content"),
        help_text=_("Type your heading as an H2 at the top, then optional supporting copy."),
    )
    button_text = CharBlock(
        required=False,
        default=_("Sign Up"),
        label=_("Button text"),
        help_text=_("Leave blank to use the site default button label."),
    )
    form_page = PageChooserBlock(
        page_type="wtrx.FormPage",
        label=_("Form page"),
        help_text=_("The FormPage whose form will be rendered inline."),
    )
    success_message = CharBlock(
        required=False,
        label=_("Success message"),
        help_text=_(
            "Message shown after successful submission. Leave blank for a generic thank-you."
        ),
    )

    class Meta:
        icon = "form"
        label = _("Sign Up (Wagtail Forms)")
        template = "wtrx/components/streamfield/blocks/signup_wagtail_forms_block.html"
        description = _(
            "A form built in this CMS (a Form page), rendered inline. Use it "
            "when the submissions should live here rather than on an external "
            "platform."
        )
        preview_value = staticmethod(_signup_wagtail_forms_preview_value)


class SuccessMessageBlock(StreamBlock):
    """
    StreamBlock for the optional thank-you content shown after a successful
    Action Network signup.

    Intentionally limited to content blocks (text, image, button) — no
    action blocks, layout blocks, or section nesting. Previously also
    offered a lightweight pull-quote block, removed when that block was
    replaced by the (much heavier, image-required) image-overlay Quote
    design — not a fit for this compact context.

    ``to_python`` coerces legacy non-list values (old RichTextBlock empty
    strings) to an empty list so existing pages load without error.
    """

    text = TextBlock()
    image = ImageBlock()
    button = ButtonBlock()

    @staticmethod
    def _coerce(value):
        """Return value as a list, coercing legacy RichTextBlock strings to []."""
        if isinstance(value, list):
            return value
        return []

    def to_python(self, value):
        # Old RichTextBlock stored a plain string (e.g. "" or "<p>...</p>").
        # Coerce any non-list value to an empty list so legacy data doesn't
        # cause "string indices must be integers" errors.
        return super().to_python(self._coerce(value))

    def bulk_to_python(self, values):
        # bulk_to_python bypasses to_python entirely; apply the same coercion
        # here so revision loading doesn't crash on legacy string values.
        return super().bulk_to_python([self._coerce(v) for v in values])

    class Meta:
        label = _("Success message content")
        required = False


class SignupActionNetworkBlock(StructBlock):
    """
    Renders an Action Network form embed widget.

    The editor pastes a full Action Network URL (e.g.
    ``https://actionnetwork.org/forms/join-30?source=direct_link&``). The block
    auto-extracts the action type and slug, then renders the v6 JS embed with
    custom styling (no Action Network CSS is loaded).

    An optional success_message field lets editors override Action Network's
    default thank-you screen. When provided, a MutationObserver in the template
    detects the AN widget's blocks and replaces it with the custom StreamField
    content.

    `content` used to be two fields — `heading` (CharBlock) and
    `description` (RichTextBlock), both optional — condensed into this one
    richtext field, same convention as ImageTextBlock. Migration
    0047_condense_more_heading_text_blocks folded every existing page's
    heading/description pair into this field's HTML on upgrade.
    """

    content = RichTextBlock(
        features=RICHTEXT_FEATURES_HEADING_H2,
        required=False,
        label=_("Content"),
        help_text=_("Type your heading as an H2 at the top, then optional supporting copy."),
    )
    action_url = URLBlock(
        label=_("Action Network URL"),
        help_text=_(
            "Paste the full Action Network form URL "
            "(e.g. https://actionnetwork.org/forms/your-form-slug)."
        ),
    )
    success_message = SuccessMessageBlock(
        required=False,
        label=_("Success message"),
        help_text=_(
            "Optional. Replaces Action Network's default thank-you screen "
            "after a successful signup."
        ),
    )
    anchor_id = CharBlock(
        required=False,
        label=_("Anchor ID"),
        help_text=_(
            "Optional. Adds an id attribute for deep-linking (e.g. 'contact' → #contact)."
        ),
    )

    def clean(self, value):
        cleaned = super().clean(value)
        action_url = cleaned.get("action_url", "")
        if action_url:
            try:
                parse_action_network_url(action_url)
            except ValidationError as exc:
                raise StructBlockValidationError(block_errors={"action_url": exc})
        return cleaned

    def get_context(self, value, parent_context=None):
        ctx = super().get_context(value, parent_context=parent_context)
        action_url = value.get("action_url", "")
        if action_url:
            try:
                parsed = parse_action_network_url(action_url)
                ctx["action_type"] = parsed["action_type"]
                ctx["slug"] = parsed["slug"]
            except ValidationError:
                ctx["action_type"] = ""
                ctx["slug"] = ""
        else:
            ctx["action_type"] = ""
            ctx["slug"] = ""
        # Pass success_message to template context for the conditional
        # thank-you override logic.
        ctx["success_message"] = value.get("success_message")
        return ctx

    class Meta:
        icon = "form"
        label = _("Sign Up (Action Network)")
        template = "wtrx/components/streamfield/blocks/signup_action_network_block.html"
        description = _(
            "An Action Network form embedded in the page, from its public URL. "
            "Supporters sign up without leaving the site."
        )
        preview_value = {
            "content": (
                "<h2>Add your name</h2>"
                "<p>Join supporters around the world calling for an end to fossil fuel expansion.</p>"
            ),
            "action_url": "https://actionnetwork.org/forms/example-petition",
        }


class SignupActionKitFormMixin:
    """
    Shared logic (no fields) for both SignupActionKitBlock (body/section
    panel, with a heading/copy `content` field) and HeroSignupActionKitBlock
    (the hero's inline CTA strip, which has no `content` field — see
    HeroSignupActionKitBlock's docstring). Not a Block subclass itself, so
    Wagtail's DeclarativeSubBlocksMetaclass never picks it up as a source of
    child blocks — only fields declared directly on the two concrete classes
    below apply.

    Auto-renders an ActionKit page's own signup form.

    Editors provide only the ActionKit page's short name. The block fetches
    that page's form via ActionKit's ``form_only=1&abs_urls=1`` embed
    mechanism (see wtrx.integrations.actionkit.fetch_embed_form_html) and
    renders the returned HTML fragment directly — whatever fields that page
    is actually configured with (name, email, custom survey questions, etc.)
    show up automatically; nothing here enumerates them. The fragment has no
    ActionKit page chrome or stylesheet, so styling is entirely ours, via CSS
    targeting ActionKit's own semantic classes (each field wraps in a
    ``{name}_box`` div carrying ``input-text``/``input-select``; text inputs
    carry ``ak-userfield-input``; see main.css's .wtr-actionkit-embed-inline
    rules, verified against a real fetched form).

    The fetched HTML — and fetch failures — are cached, since a fetch hits
    ActionKit's live server on every call. A failed fetch renders a fallback
    message instead of breaking the page.
    """

    # Which panel fills the fetched ActionKit form's own chrome has to react
    # to, mapped to the .wtr-ak-{tone} modifier class _actionkit_form.html
    # puts on the embed wrapper (see main.css). The form's default chrome —
    # a blue submit button and a --color-dark fine-print box — only reads
    # correctly against a panel that is neither of those colors, which is
    # navy and red; those two are deliberately absent here and take no
    # modifier. The rest each collide with one piece of that chrome:
    # "dark-grey" hides the fine-print box, "blue-gradient" hides the submit
    # button and the checkbox/radio accent, and the two light fills invert the
    # panel's own text, so the form's light-on-color labels have to invert
    # with them.
    #
    # The two light fills get *separate* tones even though they share that
    # text inversion, because the field boxes have to move in opposite
    # directions to stay legible as a distinct surface. Their default fill is
    # --color-neutral-50, which reads against light grey's --color-neutral-200
    # only barely, so "on-light" lifts the boxes to pure white — but the white
    # panel *is* pure white, where that same rule would erase the boxes into
    # the panel and leave only their hairline border. "on-white" therefore
    # keeps the neutral-50 default and takes the text inversion alone.
    #
    # Keys are canonical BACKGROUND_COLOR_CHOICES keys — the lookup below
    # runs the stored value through resolve_background() first, so a panel
    # still holding the pre-palette "dark" key gets the "on-dark" chrome
    # rather than silently falling through to no modifier at all.
    PANEL_TONES = {
        "dark-grey": "on-dark",
        "blue-gradient": "on-primary",
        "light-grey": "on-light",
        "white": "on-white",
    }

    # Fetch-and-cache logic used to live here as _fetch_form_html(); moved to
    # actionkit.fetch_and_cache_embed_form_html() so the footer newsletter
    # signup box (which also auto-renders a fetched ActionKit form, but has
    # no StreamField block of its own) shares the same cache key format and
    # retry window instead of keeping a second copy of this logic — see that
    # function's docstring in wtrx/integrations/actionkit.py.

    #: Stand-in for the real ActionKit form in the block picker preview.
    #: The live block fetches its form markup from the client's ActionKit
    #: instance; doing that to render a preview would put third-party traffic
    #: behind every click in the picker, and fail entirely offline or before
    #: the integration is configured. The fields mirror a default ActionKit
    #: signup form closely enough to show an editor what the block looks like.
    PREVIEW_FORM_HTML = (
        '<form class="ak-form" onsubmit="return false">'
        '<div class="ak-field"><label>Email</label>'
        '<input type="email" value="you@example.org" readonly></div>'
        '<div class="ak-field"><label>First name</label>'
        '<input type="text" value="Jane" readonly></div>'
        '<div class="ak-field"><label>Last name</label>'
        '<input type="text" value="Doe" readonly></div>'
        '<div class="ak-field"><label>Country</label>'
        '<select disabled><option>United States</option></select></div>'
        '<button type="submit" class="ak-submit">Sign the petition</button>'
        "</form>"
    )

    def get_context(self, value, parent_context=None):
        ctx = super().get_context(value, parent_context=parent_context)
        short_form_id = value.get("short_form_id", "")

        request = (parent_context or {}).get("request")
        hostname = ""
        if request is not None:
            try:
                config = IntegrationSettings.for_request(request).get_integration_config(
                    "actionkit"
                )
                hostname = config.get("hostname", "") if config else ""
            except (IntegrationSettings.DoesNotExist, Site.DoesNotExist):
                hostname = ""

        form_html = None
        if (parent_context or {}).get("is_block_preview"):
            # Never reach out to ActionKit to draw a block picker preview. The
            # harvest captures the real form markup once (see
            # `manage.py harvest_block_previews`) so the preview matches the
            # page it came from; PREVIEW_FORM_HTML covers the case where it
            # could not be captured.
            entry = self._harvested_entry() or {}
            form_html = entry.get("form_html") or self.PREVIEW_FORM_HTML
        elif hostname and short_form_id:
            form_html = actionkit.fetch_and_cache_embed_form_html(hostname, short_form_id)

        ctx["form_html"] = form_html
        ctx["actionkit_base_url"] = actionkit.base_url(hostname) if hostname else ""
        ctx["success_message"] = value.get("success_message")
        ctx["panel_tone"] = self.PANEL_TONES.get(
            resolve_background(value.get("background"), default="dark-grey"), ""
        )
        return ctx


class SignupActionKitBlock(SignupActionKitFormMixin, ContentPreviewMixin, StructBlock):
    """
    The standalone ActionKit signup panel — see SignupActionKitFormMixin for
    the shared form-fetching/caching/panel-tone logic.

    `content` used to be two fields — `heading` (CharBlock) and
    `description` (RichTextBlock), both optional — condensed into this one
    richtext field, same convention as ImageTextBlock/FeaturePanelBlock.
    `eyebrow` stays separate — it renders as its own pill, not part of the
    text flow. Migration 0047_condense_more_heading_text_blocks folded every
    existing page's heading/description pair into this field's HTML on
    upgrade.

    Distinct from HeroSignupActionKitBlock (mounted as HeroCTABlock's
    "signup" choice): that one has no `content` field at all — the hero's
    compact inline strip never rendered it, and the fields are otherwise
    identical (both classes reuse SignupActionKitFormMixin).
    """

    eyebrow = CharBlock(
        required=False,
        label=_("Eyebrow"),
        help_text=_(
            "Optional short label shown as a pill above the heading "
            "(e.g. 'Sign the Petition')."
        ),
    )
    content = RichTextBlock(
        features=RICHTEXT_FEATURES_HEADING_H2,
        required=False,
        label=_("Content"),
        help_text=_(
            "Type your heading as an H2 at the top, then optional supporting "
            "copy, shown above the ActionKit form."
        ),
    )
    background = ChoiceBlock(
        choices=BACKGROUND_COLOR_CHOICES,
        default="dark-grey",
        label=_("Background"),
        help_text=_(
            "Panel fill behind the heading, copy and form. The same palette "
            "as the page hero banner, callout and section blocks."
        ),
    )
    layout = ChoiceBlock(
        choices=[
            ("columns", _("Side by side")),
            ("vertical", _("Stacked vertically")),
        ],
        default="columns",
        label=_("Layout"),
        help_text=_(
            "Side by side splits copy and form into two columns (default). "
            "Stacked vertically runs image, copy and form down a single "
            "narrow column — better for long forms with many fields."
        ),
    )
    image = ImageChooserBlock(
        required=False,
        label=_("Image"),
    )
    image_caption = CharBlock(
        required=False,
        label=_("Image caption"),
        help_text=_("Optional caption overlaid on the image, e.g. a photo credit."),
    )
    short_form_id = CharBlock(
        label=_("ActionKit Page Shortname"),
        help_text=_(
            "The ActionKit page's short name (e.g. 'join'). Its signup form "
            "is fetched from ActionKit and rendered automatically — whatever "
            "fields that page is configured with will appear, with no further "
            "setup needed here."
        ),
    )
    anchor_id = CharBlock(
        required=False,
        label=_("Anchor ID"),
        help_text=_(
            "Optional. Adds an id attribute for deep-linking (e.g. 'contact' → #contact)."
        ),
    )
    success_message = SuccessMessageBlock(
        required=False,
        label=_("Success message"),
        help_text=_(
            "Optional. When set, a successful signup shows this message in "
            "place of the form instead of redirecting to ActionKit's own "
            "thank-you page. ActionKit's normal submission is a full-page "
            "POST directly to ActionKit, so this works by forwarding the "
            "signup through our own server (the same "
            "integrations.actionkit.submit_action REST call FormPage signups "
            "already use) instead — which does not go through ActionKit's own "
            "recaptcha check, the same trade-off that forwarding already "
            "accepts elsewhere."
        ),
    )

    class Meta:
        icon = "form"
        label = _("Sign Up (ActionKit)")
        template = "wtrx/components/streamfield/blocks/signup_actionkit_block.html"


class HeroSignupActionKitBlock(SignupActionKitFormMixin, ContentPreviewMixin, StructBlock):
    """
    The hero's inline ActionKit CTA strip — HeroCTABlock's "signup" choice
    (components/hero.html). See SignupActionKitFormMixin for the shared
    form-fetching/caching/panel-tone logic.

    No `content` field: the hero's compact rendering is a single-line strip
    sitting directly in the hero's own dark overlay, with no room (and no
    real use in practice — every existing hero CTA signup panel has always
    left it blank) for a heading/copy above the form. Use SignupActionKitBlock
    (the standalone body/section panel) when a heading is actually needed.
    Every other field carries over unchanged from SignupActionKitBlock,
    including ones the hero's compact template doesn't currently render
    (e.g. `eyebrow`) — only `content` was asked to go.
    """

    eyebrow = CharBlock(
        required=False,
        label=_("Eyebrow"),
        help_text=_(
            "Optional short label shown as a pill above the heading "
            "(e.g. 'Sign the Petition')."
        ),
    )
    background = ChoiceBlock(
        choices=BACKGROUND_COLOR_CHOICES,
        default="dark-grey",
        label=_("Background"),
        help_text=_(
            "Panel fill behind the heading, copy and form. The same palette "
            "as the page hero banner, callout and section blocks."
        ),
    )
    layout = ChoiceBlock(
        choices=[
            ("columns", _("Side by side")),
            ("vertical", _("Stacked vertically")),
        ],
        default="columns",
        label=_("Layout"),
        help_text=_(
            "Side by side splits copy and form into two columns (default). "
            "Stacked vertically runs image, copy and form down a single "
            "narrow column — better for long forms with many fields."
        ),
    )
    image = ImageChooserBlock(
        required=False,
        label=_("Image"),
    )
    image_caption = CharBlock(
        required=False,
        label=_("Image caption"),
        help_text=_("Optional caption overlaid on the image, e.g. a photo credit."),
    )
    short_form_id = CharBlock(
        label=_("ActionKit Page Shortname"),
        help_text=_(
            "The ActionKit page's short name (e.g. 'join'). Its signup form "
            "is fetched from ActionKit and rendered automatically — whatever "
            "fields that page is configured with will appear, with no further "
            "setup needed here."
        ),
    )
    anchor_id = CharBlock(
        required=False,
        label=_("Anchor ID"),
        help_text=_(
            "Optional. Adds an id attribute for deep-linking (e.g. 'contact' → #contact)."
        ),
    )
    success_message = SuccessMessageBlock(
        required=False,
        label=_("Success message"),
        help_text=_(
            "Optional. When set, a successful signup shows this message in "
            "place of the form instead of redirecting to ActionKit's own "
            "thank-you page. ActionKit's normal submission is a full-page "
            "POST directly to ActionKit, so this works by forwarding the "
            "signup through our own server (the same "
            "integrations.actionkit.submit_action REST call FormPage signups "
            "already use) instead — which does not go through ActionKit's own "
            "recaptcha check, the same trade-off that forwarding already "
            "accepts elsewhere."
        ),
    )

    class Meta:
        icon = "form"
        label = _("Sign Up (ActionKit)")
        template = "wtrx/components/streamfield/blocks/signup_actionkit_hero_block.html"


class SignupLinkBlock(StructBlock):
    """
    A simple link-out signup CTA.

    Renders a heading, optional description, and a button that links to an
    external signup URL. Use when the signup form is hosted elsewhere.

    `content` used to be two fields — `heading` (CharBlock) and
    `description` (RichTextBlock), both optional — condensed into this one
    richtext field, same convention as ImageTextBlock. Migration
    0047_condense_more_heading_text_blocks folded every existing page's
    heading/description pair into this field's HTML on upgrade.
    """

    content = RichTextBlock(
        features=RICHTEXT_FEATURES_HEADING_H2,
        required=False,
        label=_("Content"),
        help_text=_("Type your heading as an H2 at the top, then optional supporting copy."),
    )
    button_text = CharBlock(
        required=False,
        default=_("Sign Up"),
        label=_("Button text"),
        help_text=_("Leave blank to use the site default button label."),
    )
    external_url = URLBlock(
        label=_("External URL"),
        help_text=_("The external signup URL."),
    )
    anchor_id = CharBlock(
        required=False,
        label=_("Anchor ID"),
        help_text=_(
            "Optional. Adds an id attribute for deep-linking (e.g. 'contact' → #contact)."
        ),
    )

    class Meta:
        icon = "link"
        label = _("Sign Up (Link)")
        template = "wtrx/components/streamfield/blocks/signup_link_block.html"
        description = _(
            "A short sign-up prompt with a button that sends people to a form "
            "hosted elsewhere, rather than embedding one."
        )
        preview_value = {
            "content": (
                "<h2>Join the movement</h2>"
                "<p>Get campaign updates and ways to take action, straight to your inbox.</p>"
            ),
            "button_text": _("Sign up"),
            "external_url": "https://example.com/signup",
        }


# ---------------------------------------------------------------------------
# Layout blocks continued — AnnouncementBarBlock, HeroCTABlock, HeroBlock, and
# SectionBlock are defined here (after action blocks) so their nested/optional
# fields can instantiate DonateBlock and the signup classes.
# ---------------------------------------------------------------------------


class AnnouncementBarBlock(StructBlock):
    """
    A small badge/pill CTA, e.g. "Help 350.org turn things around for our
    climate." Used as one of the optional HeroBlock.cta choices.

    At most one of link_page or link_url may be set; clean() enforces this.
    """

    text = CharBlock(label=_("Text"))
    link_page = PageChooserBlock(
        required=False,
        label=_("Link page"),
        help_text=_("Internal link. Set either this or Link URL, not both."),
    )
    link_url = URLBlock(
        required=False,
        label=_("Link URL"),
        help_text=_("External link. Set either this or Link page, not both."),
    )

    def clean(self, value):
        cleaned = super().clean(value)
        errors = _validate_at_most_one_link(cleaned, {})
        if errors:
            raise StructBlockValidationError(block_errors=errors)
        return cleaned

    class Meta:
        icon = "info-circle"
        label = _("Announcement bar")
        template = "wtrx/components/streamfield/blocks/announcement_bar_block.html"


class HeroCTABlock(StreamBlock):
    """
    The hero's optional call-to-action widget: at most one of a plain link
    button, a signup bar, a donate block, or an announcement bar.
    min_num=0/max_num=1 make "at most one" a StreamField-level constraint —
    no clean() needed for it.

    `button` is the only choice the "banner" hero variant renders (as an
    outlined button with a trailing arrow, per Figma's Content Hero on The
    Great Power Shift, node 1:1225) — the other three are embedded widgets
    sized for the "full" variant's roomier layout and would overflow the
    banner's half-width text column. See components/hero.html.
    """

    button = ButtonBlock()
    signup = HeroSignupActionKitBlock()
    donate = DonateBlock()
    announcement = AnnouncementBarBlock()

    class Meta:
        min_num = 0
        max_num = 1
        label = _("Call to action")


class HeroBlock(StructBlock):
    """
    A mid-page hero banner within the StreamField body: headline + optional
    copy in a solid-color panel beside an optional image, on components/
    hero.html's "banner" variant (see CalloutBlock for the same 5-color
    system this reuses).

    Distinct from HeroMixin (which provides the dedicated hero at the top of
    a page — "full" variant on HomePage, "banner" variant on ContentPage/
    IndexPage). HeroBlock can appear anywhere in the body, on any page type,
    and always renders as "banner" — there's no full-viewport option here,
    so unlike HeroMixin there's no layout field (banner's text-left/image-
    right structure is fixed) and no cta field (banner never renders one,
    see components/hero.html).

    headline is a plain text field (mirroring HeroMixin). content is richtext
    for the supporting copy below the headline. Uses the same component
    template as the page-level hero (components/hero.html) via get_context(),
    which normalises field names so the template needs no block-type branch
    logic — only a variant branch.
    """

    headline = CharBlock(
        label=_("Headline"),
        help_text=_("The hero heading text."),
    )
    content = RichTextBlock(
        features=RICHTEXT_FEATURES_INLINE,
        required=False,
        label=_("Content"),
        help_text=_("Optional supporting copy below the headline."),
    )
    image = ImageChooserBlock(
        required=False,
        label=_("Image"),
    )
    banner_color = ChoiceBlock(
        choices=BACKGROUND_COLOR_CHOICES,
        default="navy",
        label=_("Color"),
    )

    def get_context(self, value, parent_context=None):
        ctx = super().get_context(value, parent_context=parent_context)
        # Normalise to the same shape expected by components/hero.html.
        ctx["hero"] = {
            "variant": "banner",
            "headline": value.get("headline"),
            "copy": value.get("content"),
            "copy_is_block": False,
            "image": value.get("image"),
            "video": None,  # HeroBlock does not support video; key kept for template contract
            "layout": None,  # banner variant ignores layout; key kept for template contract
            "banner_color": value.get("banner_color"),
            "cta": [],  # banner variant never renders a cta; key kept for template contract
            # Mid-page HeroBlock, not a page-level HeroMixin hero. Only the
            # gutter differs: in the body this block sits in a stack with
            # image/image_text/callout and has to line its edges up with
            # them, while the page-level hero keeps Figma's flat 16px
            # wrapper. See components/hero.html.
            "in_body": True,
        }
        return ctx

    class Meta:
        icon = "image"
        label = _("Hero")
        template = "wtrx/components/streamfield/blocks/hero_block.html"
        description = _(
            "A full-width banner with a headline, supporting copy and a "
            "coloured background -- for opening a section mid-page. A page's "
            "own hero is set on the page itself, not with this block."
        )
        preview_value = staticmethod(_hero_preview_value)


class SectionContentBlock(StreamBlock):
    """
    StreamBlock used inside SectionBlock.

    Contains all BodyStreamBlock block types except SectionBlock itself
    (to prevent infinite nesting). Declared as a named class so that
    fork sites can subclass it and override individual block types
    (e.g. swap CardBlock for a site-specific subclass) without
    duplicating the entire block list.

    Wagtail's DeclarativeSubBlocksMetaclass merges parent and child
    declared_blocks via the MRO, so a subclass only needs to redeclare
    the block(s) it wants to change.
    """

    text = TextBlock()
    lead_text = LeadTextBlock()
    image = ImageBlock()
    video = VideoBlock()
    button = ButtonBlock()
    button_group = ButtonGroupBlock()
    quote = QuoteBlock()
    raw_html = RawHTMLBlock()
    table = TableBlock()
    card = CardBlock()
    person_card = PersonCardBlock()
    person_card_grid = PersonCardGridBlock()
    card_grid = CardGridBlock()
    image_grid = ImageGridBlock()
    logo_grid = LogoGridBlock()
    image_card_list = ImageCardListBlock()
    image_text = ImageTextBlock()
    feature_panel = FeaturePanelBlock()
    card_carousel = CardCarouselBlock()
    page_cards = PageCardsBlock()
    accordion = AccordionBlock()
    callout = CalloutBlock()
    hero = HeroBlock()
    donate = DonateBlock()
    donate_fundraiseup = DonateFundraiseUpBlock()
    signup_wagtail_forms = SignupWagtailFormsBlock()
    signup_action_network = SignupActionNetworkBlock()
    signup_actionkit = SignupActionKitBlock()
    signup_link = SignupLinkBlock()

    class Meta:
        label = _("Content")


class SectionBlock(ContentPreviewMixin, StructBlock):
    """
    A full-width page section with configurable background, padding, and content.

    Content is a SectionContentBlock (a StreamBlock accepting all block types
    except SectionBlock itself, to prevent infinite nesting). No explicit
    heading field — editors use an h2 TextBlock inside the content. All action
    blocks (donate, signup variants) are included so a section can be fully
    self-contained.

    anchor_id enables deep-linking (e.g. #contact).
    """

    content = SectionContentBlock()
    background = ChoiceBlock(
        choices=BACKGROUND_COLOR_CHOICES,
        default="white",
        label=_("Background"),
        help_text=_(
            "Full-bleed fill behind the whole section. The dark colors "
            "invert the text inside it."
        ),
    )
    padding = ChoiceBlock(
        choices=SECTION_PADDING_CHOICES,
        default="md",
        label=_("Padding"),
    )
    width = ChoiceBlock(
        choices=SECTION_WIDTH_CHOICES,
        default="default",
        label=_("Content width"),
        help_text=_(
            "How wide the section's content column is. Narrow suits a text + "
            "accordion stack; wide suits a full-bleed video or image."
        ),
    )
    anchor_id = CharBlock(
        required=False,
        label=_("Anchor ID"),
        help_text=_(
            "Optional. Adds an id attribute for deep-linking (e.g. 'contact' → #contact)."
        ),
    )

    class Meta:
        icon = "placeholder"
        label = _("Section")
        template = "wtrx/components/streamfield/blocks/section_block.html"


# ---------------------------------------------------------------------------
# BodyStreamBlock
# ---------------------------------------------------------------------------


class BodyStreamBlock(StreamBlock):
    """
    The main StreamField block used on all page types.

    All block types — including all SignupBlock variants — are always
    registered here. Hiding irrelevant variants from editors is controlled
    via wagtail_hooks.py, which reads IntegrationSettings at request time
    and injects CSS to hide the block-type buttons. Never omit a block
    here to hide it.
    """

    text = TextBlock()
    lead_text = LeadTextBlock()
    image = ImageBlock()
    video = VideoBlock()
    button = ButtonBlock()
    button_group = ButtonGroupBlock()
    quote = QuoteBlock()
    raw_html = RawHTMLBlock()
    table = TableBlock()
    card = CardBlock()
    person_card = PersonCardBlock()
    person_card_grid = PersonCardGridBlock()
    card_grid = CardGridBlock()
    image_grid = ImageGridBlock()
    logo_grid = LogoGridBlock()
    image_card_list = ImageCardListBlock()
    image_text = ImageTextBlock()
    feature_panel = FeaturePanelBlock()
    card_carousel = CardCarouselBlock()
    page_cards = PageCardsBlock()
    accordion = AccordionBlock()
    callout = CalloutBlock()
    hero = HeroBlock()
    section = SectionBlock()
    donate = DonateBlock()
    donate_fundraiseup = DonateFundraiseUpBlock()
    signup_wagtail_forms = SignupWagtailFormsBlock()
    signup_action_network = SignupActionNetworkBlock()
    signup_actionkit = SignupActionKitBlock()
    signup_link = SignupLinkBlock()

    class Meta:
        icon = "list-ul"

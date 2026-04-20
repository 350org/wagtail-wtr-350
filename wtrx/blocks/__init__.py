"""
StreamField blocks for the BodyStreamBlock.

Block categories (in definition order):
  Content:  TextBlock, ImageBlock, VideoBlock, ButtonBlock, QuoteBlock,
            RawHTMLBlock, TableBlock
  Cards:    CardBlock, PersonCardBlock
  Layout:   AccordionItemBlock, CardGridBlock, AccordionBlock,
            CalloutBlock, HeroBlock
  Actions:  DonateBlock, SignupWagtailFormsBlock, SignupActionNetworkBlock,
            SignupLinkBlock
  Layout²:  SectionBlock  (defined after action blocks so its nested
            StreamBlock can instantiate the action block classes)

All blocks are assembled into BodyStreamBlock at the bottom of this file.
"""

from decimal import Decimal
import re
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
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
from wagtailmedia.blocks import VideoChooserBlock

from wtrx.constants import (
    RICHTEXT_FEATURES_FULL,
    RICHTEXT_FEATURES_INLINE,
)

# ---------------------------------------------------------------------------
# Choice constants
# ---------------------------------------------------------------------------

BUTTON_STYLE_CHOICES = [
    ("primary", _("Primary")),
    ("secondary", _("Secondary")),
    ("outline", _("Outline")),
]

CALLOUT_ALIGNMENT_CHOICES = [
    ("image-left", _("Image left")),
    ("image-right", _("Image right")),
]

SECTION_BACKGROUND_CHOICES = [
    ("light", _("Light")),
    ("dark", _("Dark")),
    ("primary", _("Primary")),
    ("secondary", _("Secondary")),
    ("muted", _("Muted")),
]

SECTION_PADDING_CHOICES = [
    ("sm", _("Small")),
    ("md", _("Medium")),
    ("lg", _("Large")),
]

# Mapping of Action Network URL path segments (plural) to embed types (singular).
# Only 'forms' is supported initially; others will be added as needed.
ACTION_NETWORK_URL_TYPES = {
    "forms": "form",
}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


def _validate_at_most_one_link(cleaned, errors):
    """
    Raise if both link_page and link_url are set.
    Modifies the errors dict in place and returns it.
    """
    if bool(cleaned.get("link_page")) and bool(cleaned.get("link_url")):
        msg = ValidationError(_("Provide either a link page or a link URL, not both."))
        errors["link_page"] = msg
        errors["link_url"] = msg
    return errors


# ---------------------------------------------------------------------------
# Content blocks
# ---------------------------------------------------------------------------


class TextBlock(RichTextBlock):
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


class ImageBlock(StructBlock):
    """
    An image with optional alt text override and caption.

    The image's built-in title is used as a fallback when alt_text is blank.
    """

    image = ImageChooserBlock(label=_("Image"))
    alt_text = CharBlock(
        required=False,
        label=_("Alt text"),
        help_text=_(
            "Overrides the image title for screen readers. Leave blank to use the image title."
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


class VideoBlock(StructBlock):
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

    Exactly one of link_page or link_url must be set. clean() enforces this.
    """

    text = CharBlock(label=_("Button text"))
    link_page = PageChooserBlock(
        required=False,
        label=_("Link page"),
        help_text=_("Internal page link. Set either this or Link URL, not both."),
    )
    link_url = URLBlock(
        required=False,
        label=_("Link URL"),
        help_text=_("External link. Set either this or Link page, not both."),
    )
    style = ChoiceBlock(
        choices=BUTTON_STYLE_CHOICES,
        default="primary",
        label=_("Style"),
    )

    def clean(self, value):
        cleaned = super().clean(value)
        errors = {}
        has_page = bool(cleaned.get("link_page"))
        has_url = bool(cleaned.get("link_url"))
        if not has_page and not has_url:
            msg = ValidationError(_("Provide either a link page or a link URL."))
            errors["link_page"] = msg
            errors["link_url"] = msg
        elif has_page and has_url:
            msg = ValidationError(
                _("Provide either a link page or a link URL, not both.")
            )
            errors["link_page"] = msg
            errors["link_url"] = msg
        if errors:
            raise StructBlockValidationError(block_errors=errors)
        return cleaned

    class Meta:
        icon = "link"
        label = _("Button")
        template = "wtrx/components/streamfield/blocks/button_block.html"


class QuoteBlock(StructBlock):
    """
    A pull quote with optional attribution.
    """

    quote = WagtailTextBlock(
        label=_("Quote"),
        help_text=_("The quotation text."),
    )
    attribution = CharBlock(
        required=False,
        label=_("Attribution"),
        help_text=_("Who said it (e.g. 'Jane Smith')."),
    )

    class Meta:
        icon = "openquote"
        label = _("Quote")
        template = "wtrx/components/streamfield/blocks/quote_block.html"


class RawHTMLBlock(WagtailRawHTMLBlock):
    """
    A raw HTML passthrough block for embed codes, custom widgets, etc.

    Use sparingly. Output is not sanitized. wagtail-localize will expose
    the raw markup to translators — brief editor guidance is recommended.
    """

    class Meta:
        icon = "code"
        label = _("Raw HTML")
        template = "wtrx/components/streamfield/blocks/raw_html_block.html"


class TableBlock(WagtailTableBlock):
    """
    A tabular data block using Wagtail's built-in table editor.
    """

    class Meta:
        icon = "table"
        label = _("Table")
        template = "wtrx/components/streamfield/blocks/table_block.html"


# ---------------------------------------------------------------------------
# Card blocks
# ---------------------------------------------------------------------------


class CardBlock(StructBlock):
    """
    A content card with a heading, optional icon, optional image, description,
    and link.

    When an icon is set, it renders at 24x24 beside the heading. Used directly
    in the StreamField and as the child block of CardGridBlock. At most one of
    link_page or link_url may be set. clean() enforces this.
    """

    icon = ImageChooserBlock(
        required=False,
        label=_("Icon"),
        help_text=_(
            "Optional small icon image (ideally square) displayed beside the heading."
        ),
    )
    heading = CharBlock(label=_("Heading"))
    description = WagtailTextBlock(
        required=False,
        label=_("Description"),
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

    def clean(self, value):
        cleaned = super().clean(value)
        errors = _validate_at_most_one_link(cleaned, {})
        if errors:
            raise StructBlockValidationError(block_errors=errors)
        return cleaned

    class Meta:
        icon = "doc-full"
        label = _("Card")
        template = "wtrx/components/streamfield/blocks/card_block.html"


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

    class Meta:
        icon = "user"
        label = _("Person")
        template = "wtrx/components/streamfield/blocks/person_card_block.html"


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


class CardGridBlock(StructBlock):
    """
    An auto-responsive grid of content cards.

    Minimum 2, maximum 12 cards. Column count is determined automatically
    by CSS (2-col on sm, 3-col on md+). No heading or column-count controls
    — editors cannot break the layout.
    """

    cards = ListBlock(
        CardBlock(),
        min_num=2,
        max_num=12,
        label=_("Cards"),
    )

    class Meta:
        icon = "grip"
        label = _("Card Grid")
        template = "wtrx/components/streamfield/blocks/card_grid_block.html"


class AccordionBlock(StructBlock):
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


class CalloutBlock(StructBlock):
    """
    An image or video + rich text side-by-side callout section.

    Stacks on mobile. Alignment (image-left / image-right) controls which
    side the media appears on desktop. Optional CTA button link.

    Exactly one of image or media_file must be set; clean() enforces this.
    At most one of link_page or link_url may be set; clean() enforces this.
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
        choices=CALLOUT_ALIGNMENT_CHOICES,
        default="image-left",
        label=_("Media alignment"),
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
        label = _("Callout")
        template = "wtrx/components/streamfield/blocks/callout_block.html"


class HeroBlock(StructBlock):
    """
    A mid-page hero section within the StreamField body.

    Distinct from HeroMixin (which provides a dedicated hero at the top of a
    page). HeroBlock can appear anywhere in the body.

    headline is a plain text field (mirroring HeroMixin). content is richtext
    for the supporting copy below the headline. Uses the same component
    template as the page-level hero (components/hero.html) via get_context(),
    which normalises field names so the template needs no branch logic.

    At most one of link_page or link_url may be set; clean() enforces this.
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

    def get_context(self, value, parent_context=None):
        ctx = super().get_context(value, parent_context=parent_context)
        # Normalise to the same shape expected by components/hero.html.
        ctx["hero"] = {
            "headline": value.get("headline"),
            "copy": value.get("content"),
            "copy_is_block": False,
            "image": value.get("image"),
            "video": None,  # HeroBlock does not support video; key kept for template contract
            "link_text": value.get("link_text"),
            "link_page": value.get("link_page"),
            "link_url": value.get("link_url"),
        }
        return ctx

    def clean(self, value):
        cleaned = super().clean(value)
        errors = _validate_at_most_one_link(cleaned, {})
        if errors:
            raise StructBlockValidationError(block_errors=errors)
        return cleaned

    class Meta:
        icon = "image"
        label = _("Hero")
        template = "wtrx/components/streamfield/blocks/hero_block.html"


# ---------------------------------------------------------------------------
# Action blocks
# ---------------------------------------------------------------------------


class DonateBlock(StructBlock):
    """
    A donation call-to-action section.

    Behavior (platform, base URL, suggested amounts) is driven by
    IntegrationSettings at render time — not hardcoded here. The
    override_amounts and override_url fields let editors override the
    site-wide defaults on a per-block basis.
    """

    heading = CharBlock(
        label=_("Heading"),
        help_text=_("Donation section heading."),
    )
    description = RichTextBlock(
        features=RICHTEXT_FEATURES_INLINE,
        required=False,
        label=_("Description"),
        help_text=_("Optional supporting text below the heading."),
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

    class Meta:
        icon = "pick"
        label = _("Donate")
        template = "wtrx/components/streamfield/blocks/donate_block.html"


class SignupWagtailFormsBlock(StructBlock):
    """
    Renders a Wagtail FormPage's form inline.

    AJAX submission posts to form_page.url. On success, the form is replaced
    with success_message (or a generic fallback). The form instance is
    instantiated in the template via form_page.get_form_class()().
    """

    heading = CharBlock(
        label=_("Heading"),
        help_text=_("Signup section heading."),
    )
    description = RichTextBlock(
        features=RICHTEXT_FEATURES_INLINE,
        required=False,
        label=_("Description"),
        help_text=_("Optional supporting text below the heading."),
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


class SuccessMessageBlock(StreamBlock):
    """
    StreamBlock for the optional thank-you content shown after a successful
    Action Network signup.

    Intentionally limited to content blocks (text, image, button, quote) —
    no action blocks, layout blocks, or section nesting.

    ``to_python`` coerces legacy non-list values (old RichTextBlock empty
    strings) to an empty list so existing pages load without error.
    """

    text = TextBlock()
    image = ImageBlock()
    button = ButtonBlock()
    quote = QuoteBlock()

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
    """

    heading = CharBlock(
        label=_("Heading"),
        help_text=_("Signup section heading."),
    )
    description = RichTextBlock(
        features=RICHTEXT_FEATURES_INLINE,
        required=False,
        label=_("Description"),
        help_text=_("Optional supporting text below the heading."),
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


class SignupLinkBlock(StructBlock):
    """
    A simple link-out signup CTA.

    Renders a heading, optional description, and a button that links to an
    external signup URL. Use when the signup form is hosted elsewhere.
    """

    heading = CharBlock(
        label=_("Heading"),
        help_text=_("Signup section heading."),
    )
    description = RichTextBlock(
        features=RICHTEXT_FEATURES_INLINE,
        required=False,
        label=_("Description"),
        help_text=_("Optional supporting text below the heading."),
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

    class Meta:
        icon = "link"
        label = _("Sign Up (Link)")
        template = "wtrx/components/streamfield/blocks/signup_link_block.html"


# ---------------------------------------------------------------------------
# Layout blocks continued — SectionBlock is defined here (after action blocks)
# so its nested StreamBlock can instantiate DonateBlock and the signup classes.
# ---------------------------------------------------------------------------


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
    image = ImageBlock()
    video = VideoBlock()
    button = ButtonBlock()
    quote = QuoteBlock()
    raw_html = RawHTMLBlock()
    table = TableBlock()
    card = CardBlock()
    person_card = PersonCardBlock()
    card_grid = CardGridBlock()
    accordion = AccordionBlock()
    callout = CalloutBlock()
    hero = HeroBlock()
    donate = DonateBlock()
    signup_wagtail_forms = SignupWagtailFormsBlock()
    signup_action_network = SignupActionNetworkBlock()
    signup_link = SignupLinkBlock()

    class Meta:
        label = _("Content")


class SectionBlock(StructBlock):
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
        choices=SECTION_BACKGROUND_CHOICES,
        default="light",
        label=_("Background"),
    )
    padding = ChoiceBlock(
        choices=SECTION_PADDING_CHOICES,
        default="md",
        label=_("Padding"),
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
    image = ImageBlock()
    video = VideoBlock()
    button = ButtonBlock()
    quote = QuoteBlock()
    raw_html = RawHTMLBlock()
    table = TableBlock()
    card = CardBlock()
    person_card = PersonCardBlock()
    card_grid = CardGridBlock()
    accordion = AccordionBlock()
    callout = CalloutBlock()
    hero = HeroBlock()
    section = SectionBlock()
    donate = DonateBlock()
    signup_wagtail_forms = SignupWagtailFormsBlock()
    signup_action_network = SignupActionNetworkBlock()
    signup_link = SignupLinkBlock()

    class Meta:
        icon = "list-ul"

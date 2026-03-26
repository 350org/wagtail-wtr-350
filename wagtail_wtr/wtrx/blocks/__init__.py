"""
StreamField blocks for the BodyStreamBlock.

Block categories (in definition order):
  Content:  TextBlock, ImageBlock, VideoBlock, ButtonBlock, QuoteBlock,
            RawHTMLBlock, TableBlock
  Cards:    CardBlock, PersonCardBlock
  Layout:   AccordionItemBlock, CardGridBlock, AccordionBlock,
            CalloutBlock, HeroBlock, SectionBlock
  Actions:  DonateBlock, SignupWagtailFormsBlock, SignupActionNetworkBlock,
            SignupLinkBlock

All blocks are assembled into BodyStreamBlock at the bottom of this file.
"""

from decimal import Decimal

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

from wagtail_wtr.wtrx.constants import (
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
    ("muted", _("Muted")),
]

SECTION_PADDING_CHOICES = [
    ("sm", _("Small")),
    ("md", _("Medium")),
    ("lg", _("Large")),
]

ACTION_NETWORK_ACTION_TYPE_CHOICES = [
    ("petition", _("Petition")),
    ("form", _("Signup form")),
    ("fundraising_page", _("Fundraising page")),
    ("ticketed_event", _("Ticketed event")),
    ("letter", _("Letter")),
]

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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
        template = "components/streamfield/blocks/text_block.html"


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
        template = "components/streamfield/blocks/image_block.html"


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
        template = "components/streamfield/blocks/video_block.html"


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
        template = "components/streamfield/blocks/button_block.html"


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
        template = "components/streamfield/blocks/quote_block.html"


class RawHTMLBlock(WagtailRawHTMLBlock):
    """
    A raw HTML passthrough block for embed codes, custom widgets, etc.

    Use sparingly. Output is not sanitized. wagtail-localize will expose
    the raw markup to translators — brief editor guidance is recommended.
    """

    class Meta:
        icon = "code"
        label = _("Raw HTML")
        template = "components/streamfield/blocks/raw_html_block.html"


class TableBlock(WagtailTableBlock):
    """
    A tabular data block using Wagtail's built-in table editor.
    """

    class Meta:
        icon = "table"
        label = _("Table")
        template = "components/streamfield/blocks/table_block.html"


# ---------------------------------------------------------------------------
# Card blocks
# ---------------------------------------------------------------------------


class CardBlock(StructBlock):
    """
    A content card with a heading, optional image, description, and link.

    Used directly in the StreamField and as the child block of CardGridBlock.
    At most one of link_page or link_url may be set. clean() enforces this.
    """

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
        template = "components/streamfield/blocks/card_block.html"


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
        template = "components/streamfield/blocks/person_card_block.html"


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
        template = "components/streamfield/blocks/card_grid_block.html"


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
        template = "components/streamfield/blocks/accordion_block.html"


class CalloutBlock(StructBlock):
    """
    An image + rich text side-by-side callout section.

    Stacks on mobile. Alignment (image-left / image-right) controls which
    side the image appears on desktop. Optional CTA button link. At most one
    of link_page or link_url may be set; clean() enforces this.
    """

    content = RichTextBlock(
        features=RICHTEXT_FEATURES_FULL,
        label=_("Content"),
    )
    image = ImageChooserBlock(label=_("Image"))
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
        label=_("Image alignment"),
    )

    def clean(self, value):
        cleaned = super().clean(value)
        errors = _validate_at_most_one_link(cleaned, {})
        if errors:
            raise StructBlockValidationError(block_errors=errors)
        return cleaned

    class Meta:
        icon = "image"
        label = _("Callout")
        template = "components/streamfield/blocks/callout_block.html"


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
        template = "components/streamfield/blocks/hero_block.html"


class SectionBlock(StructBlock):
    """
    A full-width page section with configurable background, padding, and content.

    Content is a nested StreamBlock accepting all blocks except SectionBlock
    itself (to prevent infinite nesting). No explicit heading field — editors
    use an h2 TextBlock inside the content.

    anchor_id enables deep-linking (e.g. #contact).
    """

    content = StreamBlock(
        [
            ("text", TextBlock()),
            ("image", ImageBlock()),
            ("video", VideoBlock()),
            ("button", ButtonBlock()),
            ("quote", QuoteBlock()),
            ("raw_html", RawHTMLBlock()),
            ("table", TableBlock()),
            ("card_grid", CardGridBlock()),
            ("accordion", AccordionBlock()),
            ("callout", CalloutBlock()),
        ],
        label=_("Content"),
    )
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
        template = "components/streamfield/blocks/section_block.html"


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
        template = "components/streamfield/blocks/donate_block.html"


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
        page_type="wagtail_wtr_forms.FormPage",
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
        template = "components/streamfield/blocks/signup_wagtail_forms_block.html"


class SignupActionNetworkBlock(StructBlock):
    """
    Renders an Action Network JS widget.

    The action_network_id is the identifier for the specific Action Network
    action (petition, signup form, etc.). The JS widget is embedded in the
    template using Action Network's standard embed code.
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
    action_type = ChoiceBlock(
        choices=ACTION_NETWORK_ACTION_TYPE_CHOICES,
        default="petition",
        label=_("Action type"),
        help_text=_("The type of Action Network action being embedded."),
    )
    action_network_id = CharBlock(
        label=_("Action Network ID"),
        help_text=_(
            "The Action Network action identifier (e.g. 'abc12345-...'). "
            "Found in the Action Network embed code."
        ),
    )

    class Meta:
        icon = "form"
        label = _("Sign Up (Action Network)")
        template = "components/streamfield/blocks/signup_action_network_block.html"


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
        template = "components/streamfield/blocks/signup_link_block.html"


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

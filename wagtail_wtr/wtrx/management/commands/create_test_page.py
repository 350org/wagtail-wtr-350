"""
create_test_page management command.

Creates a ContentPage under the site root page that exercises every block type
in BodyStreamBlock. Useful for visual QA — load the page to verify all blocks
render without errors.

Only runs when DEBUG=True.

Usage:
    python manage.py create_test_page
    python manage.py create_test_page --slug my-test-page
    python manage.py create_test_page --force  # overwrite if page already exists

The command is safe to run multiple times with --force. Without --force it
skips creation if a page with the given slug already exists under the home page.
"""

import json
import os
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


_RICHTEXT_PARAGRAPH = "<p>This is a sample paragraph of rich text. It contains <strong>bold</strong>, <em>italic</em>, and a <a href='#'>link</a>.</p>"

_SAMPLE_TABLE = {
    "data": [
        ["Candidate", "Party", "District"],
        ["Alice Example", "Democratic", "3rd"],
        ["Bob Sample", "Republican", "3rd"],
    ],
    "first_row_is_table_header": True,
    "first_col_is_header": False,
    "table_caption": "Sample candidate table",
}


def _make_test_image():
    """
    Create and return a CustomImage in the database loaded from the committed
    fixture at fixtures/placeholder.jpg (1200×800, indigo background with label).

    Using a real JPEG ensures image-bearing blocks render visually during QA
    (hero, callout, card, person card, image block).
    """
    import os

    from django.conf import settings as django_settings
    from django.core.files.uploadedfile import SimpleUploadedFile

    from wagtail_wtr.wtrx.images import CustomImage

    # BASE_DIR is the repo root (parent of manage.py / wagtail_wtr/).
    fixture_path = os.path.join(django_settings.BASE_DIR, "fixtures", "placeholder.png")
    with open(fixture_path, "rb") as fh:
        png_bytes = fh.read()

    uploaded = SimpleUploadedFile(
        "placeholder.png", png_bytes, content_type="image/png"
    )
    image = CustomImage(title="Placeholder Image", file=uploaded)
    image.save()
    return image


def _text_block():
    return {"type": "text", "value": _RICHTEXT_PARAGRAPH}


def _image_block_full(image_id):
    """ImageBlock with caption and explicit alt text."""
    return {
        "type": "image",
        "value": {
            "image": image_id,
            "alt_text": "A test image with explicit alt text",
            "caption": "Sample image caption",
        },
    }


def _image_block_minimal(image_id):
    """ImageBlock without optional fields."""
    return {
        "type": "image",
        "value": {
            "image": image_id,
            "alt_text": "",
            "caption": "",
        },
    }


def _video_block():
    return {
        "type": "video",
        "value": {
            "embed_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "media_file": None,
            "caption": "Sample video caption",
        },
    }


def _button_block_primary():
    return {
        "type": "button",
        "value": {
            "text": "Primary Button",
            "link_page": None,
            "link_url": "https://example.com",
            "style": "primary",
        },
    }


def _button_block_secondary():
    return {
        "type": "button",
        "value": {
            "text": "Secondary Button",
            "link_page": None,
            "link_url": "https://example.com",
            "style": "secondary",
        },
    }


def _button_block_outline():
    return {
        "type": "button",
        "value": {
            "text": "Outline Button",
            "link_page": None,
            "link_url": "https://example.com",
            "style": "outline",
        },
    }


def _quote_block_with_attribution():
    return {
        "type": "quote",
        "value": {
            "quote": "The change we need starts with each of us showing up.",
            "attribution": "A. Organizer",
        },
    }


def _quote_block_no_attribution():
    return {
        "type": "quote",
        "value": {
            "quote": "Unattributed quote — no attribution field set.",
            "attribution": "",
        },
    }


def _raw_html_block():
    return {
        "type": "raw_html",
        "value": "<p><em>Raw HTML block — rendered verbatim.</em></p>",
    }


def _table_block():
    return {"type": "table", "value": _SAMPLE_TABLE}


def _card_block_full(image_id):
    """Standalone CardBlock with image, icon, description, and link."""
    return {
        "type": "card",
        "value": {
            "icon": image_id,
            "heading": "Standalone Card (with image)",
            "description": "This is a standalone card with an image and an external link.",
            "image": image_id,
            "link_page": None,
            "link_url": "https://example.com",
        },
    }


def _card_block_minimal():
    """Standalone CardBlock — heading only, no image, no icon, no link."""
    return {
        "type": "card",
        "value": {
            "icon": None,
            "heading": "Standalone Card (minimal)",
            "description": "",
            "image": None,
            "link_page": None,
            "link_url": None,
        },
    }


def _person_card_block_full(image_id):
    """PersonCardBlock with all fields populated."""
    return {
        "type": "person_card",
        "value": {
            "name": "Jane Sample",
            "role": "Campaign Manager",
            "image": image_id,
            "bio": "Jane has worked in grassroots organizing for over a decade.",
            "email": "jane@example.com",
            "phone": "555-867-5309",
            "website": "https://example.com",
        },
    }


def _person_card_block_minimal():
    """PersonCardBlock with only the required name field."""
    return {
        "type": "person_card",
        "value": {
            "name": "Bob Minimal",
            "role": "",
            "image": None,
            "bio": "",
            "email": "",
            "phone": "",
            "website": "",
        },
    }


def _card_grid_block(image_id):
    """CardGridBlock with a mix of cards: image/no-image, icon/no-icon, link/no-link."""
    return {
        "type": "card_grid",
        "value": {
            "cards": [
                {
                    "icon": image_id,
                    "image": image_id,
                    "heading": "Card Grid — With Image",
                    "description": "This card has an image and an external link.",
                    "link_page": None,
                    "link_url": "https://example.com",
                },
                {
                    "icon": None,
                    "image": None,
                    "heading": "Card Grid — No Image",
                    "description": "This card has no image but still has a link.",
                    "link_page": None,
                    "link_url": "https://example.com",
                },
                {
                    "icon": None,
                    "image": None,
                    "heading": "Card Grid — Description Only",
                    "description": "This card has no image and no link — description only.",
                    "link_page": None,
                    "link_url": None,
                },
            ]
        },
    }


def _accordion_block():
    return {
        "type": "accordion",
        "value": {
            "items": [
                {
                    "title": "What is this accordion?",
                    "content": _RICHTEXT_PARAGRAPH,
                },
                {
                    "title": "How do I use it?",
                    "content": "<p>Click the title to expand or collapse this panel.</p>",
                },
            ]
        },
    }


def _callout_block_image_left(image_id):
    """CalloutBlock: image on the left, with a CTA link."""
    return {
        "type": "callout",
        "value": {
            "content": "<p>Callout block with the image aligned to the <strong>left</strong>. This supports rich text and a CTA button.</p>",
            "image": image_id,
            "alignment": "image-left",
            "link_text": "Learn More",
            "link_page": None,
            "link_url": "https://example.com",
        },
    }


def _callout_block_image_right(image_id):
    """CalloutBlock: image on the right, no CTA."""
    return {
        "type": "callout",
        "value": {
            "content": "<p>Callout block with the image aligned to the <strong>right</strong>. No CTA button on this one.</p>",
            "image": image_id,
            "alignment": "image-right",
            "link_text": "",
            "link_page": None,
            "link_url": None,
        },
    }


def _hero_block_full():
    """HeroBlock with headline, copy, and a CTA link."""
    return {
        "type": "hero",
        "value": {
            "headline": "Hero Block Inside Body",
            "content": "<p>This hero appears mid-page inside the StreamField body.</p>",
            "image": None,
            "link_text": "Call to Action",
            "link_page": None,
            "link_url": "https://example.com",
        },
    }


def _hero_block_minimal():
    """HeroBlock with only a headline — no copy, no image, no CTA."""
    return {
        "type": "hero",
        "value": {
            "headline": "Minimal Hero — Headline Only",
            "content": "",
            "image": None,
            "link_text": "",
            "link_page": None,
            "link_url": None,
        },
    }


def _donate_block_full():
    """DonateBlock with override amounts and override URL."""
    return {
        "type": "donate",
        "value": {
            "heading": "Support Our Campaign",
            "description": "<p>Every dollar helps us reach more voters.</p>",
            "button_text": "Donate Now",
            "override_amounts": ["10.00", "25.00", "50.00", "100.00"],
            "override_url": "https://secure.actblue.com/donate/example",
        },
    }


def _donate_block_minimal():
    """DonateBlock with no overrides — uses site-wide settings fallback."""
    return {
        "type": "donate",
        "value": {
            "heading": "Donate (using site defaults)",
            "description": "",
            "button_text": "",
            "override_amounts": [],
            "override_url": "",
        },
    }


def _signup_link_block():
    return {
        "type": "signup_link",
        "value": {
            "heading": "Join Our Movement",
            "description": "<p>Sign up to stay informed and take action.</p>",
            "button_text": "Sign Up",
            "external_url": "https://actionnetwork.org/forms/example",
        },
    }


def _signup_action_network_block():
    return {
        "type": "signup_action_network",
        "value": {
            "heading": "Action Network Signup",
            "description": "<p>Sign up via Action Network.</p>",
            "action_url": "https://actionnetwork.org/forms/join-30",
            "success_message": "",
        },
    }


def _section_block(background, padding, anchor_suffix, image_id):
    """
    A SectionBlock wrapping a representative mix of inner blocks.
    ``background`` is one of 'light', 'dark', 'primary', 'muted'.
    ``padding`` is one of 'sm', 'md', 'lg'.
    """
    anchor = (
        f"section-{background}"
        if not anchor_suffix
        else f"section-{background}-{anchor_suffix}"
    )
    inner_blocks = [
        _text_block(),
        _button_block_primary(),
        _quote_block_with_attribution(),
        _table_block(),
        _accordion_block(),
        _donate_block_full(),
        _signup_link_block(),
        _image_block_full(image_id),
        _card_grid_block(image_id),
        _callout_block_image_left(image_id),
    ]
    return {
        "type": "section",
        "value": {
            "background": background,
            "padding": padding,
            "anchor_id": anchor,
            "content": inner_blocks,
        },
    }


# Full list of flat (non-section) blocks for the top-level body.
# Each entry is a callable that accepts an image_id argument.
def _build_flat_blocks(image_id):
    return [
        _text_block(),
        _image_block_full(image_id),
        _image_block_minimal(image_id),
        _video_block(),
        _button_block_primary(),
        _button_block_secondary(),
        _button_block_outline(),
        _quote_block_with_attribution(),
        _quote_block_no_attribution(),
        _raw_html_block(),
        _table_block(),
        _card_block_full(image_id),
        _card_block_minimal(),
        _person_card_block_full(image_id),
        _person_card_block_minimal(),
        _card_grid_block(image_id),
        _accordion_block(),
        _callout_block_image_left(image_id),
        _callout_block_image_right(image_id),
        _hero_block_full(),
        _hero_block_minimal(),
        _donate_block_full(),
        _donate_block_minimal(),
        _signup_link_block(),
        _signup_action_network_block(),
    ]


# (background, padding, anchor_suffix) tuples for section permutations
_SECTION_VARIANTS = [
    ("light", "md", ""),
    ("muted", "md", ""),
    ("dark", "md", ""),
    ("primary", "md", ""),
    ("light", "sm", "sm"),
    ("light", "lg", "lg"),
]


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
        from wagtail.models import Page, Site

        from wagtail_wtr.pages.models import ContentPage

        slug = options["slug"]
        force = options["force"]

        # Locate the default site's root page to attach the test page under.
        try:
            site = Site.objects.get(is_default_site=True)
        except Site.DoesNotExist:
            raise CommandError(
                "No default Site found. Run 'python manage.py setup_site' first."
            )

        parent = site.root_page.specific

        # Check for existing page
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

        # Create a shared test image for all image-bearing blocks.
        image = _make_test_image()
        image_id = image.pk

        # Build the StreamField body value
        body_data = []

        # 1. All flat block types (every block, every permutation)
        body_data.extend(_build_flat_blocks(image_id))

        # 2. SectionBlock permutations (4 backgrounds × 1 padding + 2 extra padding)
        for background, padding, suffix in _SECTION_VARIANTS:
            body_data.append(_section_block(background, padding, suffix, image_id))

        # Assign stable IDs so the StreamField JSON is well-formed
        for block in body_data:
            block["id"] = str(uuid.uuid4())
            # Assign IDs to nested blocks inside sections
            if block["type"] == "section":
                for inner in block["value"].get("content", []):
                    inner["id"] = str(uuid.uuid4())

        page = ContentPage(
            title="Block Test Page",
            slug=slug,
            body=json.dumps(body_data),
        )
        parent.add_child(instance=page)

        self.stdout.write(
            self.style.SUCCESS(
                f'  Created test page "{page.title}" (pk={page.pk}) at /{slug}/'
            )
        )
        self.stdout.write(f"  Visit: http://localhost:8000/{slug}/")

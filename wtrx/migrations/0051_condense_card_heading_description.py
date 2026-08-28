# Folds CardBlock's and ImageCardListItemBlock's separate heading/description
# fields into each block's single `content` richtext field, without losing
# any existing content. Same technique as 0045/0047, with one twist: unlike
# every block condensed so far, `description` on both these blocks was a
# plain TextBlock (raw text, no HTML at all) rather than an already-richtext
# field, so it needs escaping AND wrapping in a <p> here, not just the
# heading.
#
# The bigger twist: CardBlock appears three ways in the stored JSON, at two
# different nesting depths relative to its own "type" key.
#   - As a standalone body/section block (`card = CardBlock()` in
#     BodyStreamBlock/SectionContentBlock): a normal StreamBlock entry,
#     `{"type": "card", "value": {...the card's own fields...}}` -- the
#     type-keyed shape 0045/0047 already handle.
#   - Nested inside CardGridBlock.cards / CardCarouselBlock.cards
#     (`ListBlock(CardBlock())` / `ListBlock(CarouselCardBlock())`): each
#     list item is `{"id": ..., "type": "item", "value": {...the card's own
#     fields...}}` -- ListBlock wraps its items too, just with a generic
#     "item" type rather than a StreamBlock child's real type name, so a
#     naive type-keyed match on "card" would never find these (and looking
#     for "heading" directly on the list item, instead of on
#     item["value"], finds nothing either -- both wrong assumptions this
#     migration got wrong on its first pass; see AGENTS.md pitfall #46 for
#     why "the test suite went green" doesn't prove a migration this shape
#     of bug can't hide behind).
#   - ImageCardListItemBlock nested inside ImageCardListBlock.cards is the
#     same "item"-wrapped shape, one level further down (keyed by the
#     *parent* type "image_card_list").
#
# So this migration keys off the *parent* block's type to reach the "cards"
# list, in addition to the ordinary type-keyed match for standalone "card"
# entries, and unwraps each list item's "value" before looking for
# "heading" -- rather than trying to recognise a bare CardBlock/
# ImageCardListItemBlock dict sitting unwrapped in the list.
import json

from django.db import migrations
from django.utils.html import escape

# Parent block types whose "cards" ListBlock holds CardBlock/CarouselCardBlock/
# ImageCardListItemBlock values needing this same heading/description merge.
CARDS_LIST_PARENT_TYPES = {"card_grid", "card_carousel", "image_card_list"}


def _combine_card(value):
    """Fold value's heading/description into its `content` richtext field, in place."""
    heading = escape(value.pop("heading", "") or "")
    description = escape(value.pop("description", "") or "")
    content = f"<h3>{heading}</h3>" if heading else ""
    if description:
        content += f"<p>{description}</p>"
    value["content"] = content


def _rewrite(node):
    """
    Walk parsed StreamField JSON, condensing card heading/description fields
    into `content` in place. Returns True if anything changed.
    """
    changed = False
    if isinstance(node, list):
        for item in node:
            changed |= _rewrite(item)
    elif isinstance(node, dict):
        block_type = node.get("type")
        value = node.get("value")
        if block_type == "card" and isinstance(value, dict) and "heading" in value:
            _combine_card(value)
            changed = True
        elif (
            block_type in CARDS_LIST_PARENT_TYPES
            and isinstance(value, dict)
            and isinstance(value.get("cards"), list)
        ):
            # ListBlock items are themselves wrapped -- {"id", "type": "item",
            # "value": {...actual card fields...}} -- not bare dicts, unlike
            # what a StreamBlock's own entries look like. The real card value
            # is one level deeper, under "value".
            for card_item in value["cards"]:
                if not isinstance(card_item, dict):
                    continue
                card_value = card_item.get("value")
                if isinstance(card_value, dict) and "heading" in card_value:
                    _combine_card(card_value)
                    changed = True
        for child in node.values():
            if isinstance(child, (list, dict)):
                changed |= _rewrite(child)
    return changed


def _stream_field_names(model):
    from wagtail.fields import StreamField

    return [f.name for f in model._meta.get_fields() if isinstance(f, StreamField)]


def forwards(apps, schema_editor):
    Revision = apps.get_model("wagtailcore", "Revision")
    ContentType = apps.get_model("contenttypes", "ContentType")

    content_type_ids = []
    for model in [m for m in apps.get_models() if m._meta.app_label == "wtrx"]:
        field_names = _stream_field_names(model)
        if not field_names:
            continue

        for obj in model.objects.all().iterator():
            dirty = False
            for name in field_names:
                raw = list(getattr(obj, name).raw_data)
                if _rewrite(raw):
                    setattr(obj, name, json.dumps(raw))
                    dirty = True
            if dirty:
                obj.save(update_fields=field_names)

        ct = ContentType.objects.filter(
            app_label="wtrx", model=model._meta.model_name
        ).first()
        if ct is not None:
            content_type_ids.append((ct.pk, field_names))

    for ct_id, field_names in content_type_ids:
        for revision in Revision.objects.filter(content_type_id=ct_id).iterator():
            content = revision.content
            if not isinstance(content, dict):
                continue
            dirty = False
            for name in field_names:
                stored = content.get(name)
                if not isinstance(stored, str) or not stored.strip():
                    continue
                try:
                    parsed = json.loads(stored)
                except ValueError:
                    continue
                if _rewrite(parsed):
                    content[name] = json.dumps(parsed)
                    dirty = True
            if dirty:
                revision.content = content
                revision.save(update_fields=["content"])


class Migration(migrations.Migration):
    dependencies = [
        ("wtrx", "0050_alter_blogs_hero_cta_alter_contentpage_hero_cta_and_more"),
    ]

    operations = [
        # Not reversible -- same reasoning as 0045/0047.
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

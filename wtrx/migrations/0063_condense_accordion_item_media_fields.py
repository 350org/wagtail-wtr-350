# Folds AccordionItemBlock's separate `image`/`video` StructBlock fields
# into its `content` field, converting `content` from a plain richtext
# string into a StreamBlock list (AccordionItemContentBlock: text/image/
# video), so "no image"/"no video" is expressed as "no such block in the
# list" instead of a present-but-blank struct value. That StructBlock-field
# shape is what made ImageBlock.image (a required ImageChooserBlock) and
# VideoBlock.clean() (which always demands exactly one of embed_url/
# media_file) trip a validation error on every item genuinely missing one
# -- most of them, since real items have zero, one, or two of image/video,
# never a "blank but present" struct. See AGENTS.md pitfall #51.
#
# Same technique as 0045/0047/0051: walk every wtrx model's StreamField
# raw_data (and every stored Revision.content blob for that model, since
# each revision is its own independent JSON copy) and every existing page's
# body, recursively, looking for `{"type": "accordion", ...}` at any depth
# -- the generic recursive walk (the trailing `for child in node.values()`
# in _rewrite()) is what reaches `accordion` however deeply it's nested
# (top-level body, inside a `section`'s content, inside a `timeline`
# year's content, ...) without needing to hand-enumerate every parent
# block type the way 0051 had to for CardBlock's few known ListBlock
# parents.
#
# AccordionBlock.items is itself a ListBlock(AccordionItemBlock()), so per
# AGENTS.md pitfall #48, each item may be either the bare legacy shape (a
# plain dict of the item's own fields -- what a raw import script, never
# saved once through the admin, still has) or the wrapped
# {"id", "type": "item", "value": {...}} shape Wagtail's ListBlock
# normalizes to on every admin save. This handles both.
#
# Idempotent: an item with no "image"/"video" keys and a non-string
# `content` (i.e., already migrated) is left untouched, so re-running this
# is safe.
import json
import uuid

from django.db import migrations


def _condense_accordion_item(item_value):
    """Fold item_value's content/image/video into a single StreamBlock `content` list, in place."""
    old_content = item_value.pop("content", "")
    new_content = []
    if isinstance(old_content, str) and old_content.strip():
        new_content.append({"type": "text", "value": old_content, "id": str(uuid.uuid4())})

    image_value = item_value.pop("image", None)
    if isinstance(image_value, dict) and image_value.get("image"):
        new_content.append(
            {
                "type": "image",
                "value": {
                    "image": image_value.get("image"),
                    "alt_text": image_value.get("alt_text", "") or "",
                    "caption": image_value.get("caption", "") or "",
                },
                "id": str(uuid.uuid4()),
            }
        )

    video_value = item_value.pop("video", None)
    if isinstance(video_value, dict) and (video_value.get("embed_url") or video_value.get("media_file")):
        new_content.append(
            {
                "type": "video",
                "value": {
                    "embed_url": video_value.get("embed_url", "") or "",
                    "media_file": video_value.get("media_file"),
                    "caption": video_value.get("caption", "") or "",
                },
                "id": str(uuid.uuid4()),
            }
        )

    item_value["content"] = new_content


def _needs_condensing(item_value):
    return (
        "image" in item_value
        or "video" in item_value
        or isinstance(item_value.get("content"), str)
    )


def _rewrite(node):
    """
    Walk parsed StreamField JSON, condensing accordion item image/video
    fields into `content` in place. Returns True if anything changed.
    """
    changed = False
    if isinstance(node, list):
        for item in node:
            changed |= _rewrite(item)
    elif isinstance(node, dict):
        block_type = node.get("type")
        value = node.get("value")
        if block_type == "accordion" and isinstance(value, dict) and isinstance(value.get("items"), list):
            for list_item in value["items"]:
                if not isinstance(list_item, dict):
                    continue
                # ListBlock items may be bare (a raw import script's own
                # writes) or wrapped {"id","type":"item","value":{...}}
                # (normal admin-save shape) -- AGENTS.md pitfall #48.
                if "value" in list_item and "type" in list_item:
                    item_value = list_item["value"]
                else:
                    item_value = list_item
                if isinstance(item_value, dict) and _needs_condensing(item_value):
                    _condense_accordion_item(item_value)
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
        ("wtrx", "0062_alter_contentpage_body_alter_homepage_body_and_more"),
    ]

    operations = [
        # Not reversible -- same reasoning as 0045/0047/0051.
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

# Second wave of 0045_condense_heading_text_blocks: folds the separate
# heading (+ eyebrow-adjacent) fields of SignupActionKitBlock,
# DonateFundraiseUpBlock, DonateBlock, SignupWagtailFormsBlock,
# SignupActionNetworkBlock, SignupLinkBlock and PageCardsBlock into each
# block's single `content` richtext field, without losing any existing
# content.
#
# Unlike wave one, none of these seven already used "content" as their
# pre-existing body-copy field name — each used "description" (or, for
# PageCardsBlock, "subheading", which despite its name rendered as a plain
# paragraph, not an H3) — so there is no TEXT_SOURCE_FIELD name collision to
# worry about here (see AGENTS.md pitfall #46 for the wave-one trap this
# avoids by construction: every source field below really is the pre-existing
# body-copy field, not "content" already meaning something else).
#
# `eyebrow` on SignupActionKitBlock is untouched -- it renders as its own
# pill, not part of the text flow, and was never part of this merge.
#
# Same technique as 0040_unify_block_background_values and
# 0045_condense_heading_text_blocks: walk the raw StreamField JSON for both
# live objects and their revisions.
import json

from django.db import migrations
from django.utils.html import escape

# Which field held the pre-existing body copy, per block type. SignupActionKitBlock
# is registered under two different stream keys -- "signup_actionkit" in
# BodyStreamBlock/SectionContentBlock, but "signup" inside HeroCTABlock (the
# hero's CTA choice, components/hero.html) -- so both need an entry here or
# every hero CTA signup panel would be silently skipped.
TEXT_SOURCE_FIELD = {
    "signup_actionkit": "description",
    "signup": "description",
    "donate_fundraiseup": "description",
    "donate": "description",
    "signup_wagtail_forms": "description",
    "signup_action_network": "description",
    "signup_link": "description",
    "page_cards": "subheading",
}


def _combine(block_type, value):
    """Fold value's dropped heading field into its `content` richtext field, in place."""
    heading = escape(value.pop("heading", "") or "")
    existing_content = value.pop(TEXT_SOURCE_FIELD[block_type], "") or ""
    if heading:
        value["content"] = f"<h2>{heading}</h2>{existing_content}"
    else:
        # heading was optional on every one of these blocks -- a block with
        # no heading keeps just its existing body copy, unwrapped.
        value["content"] = existing_content


def _rewrite(node):
    """
    Walk parsed StreamField JSON, condensing heading fields into `content` in
    place. Returns True if anything changed.
    """
    changed = False
    if isinstance(node, list):
        for item in node:
            changed |= _rewrite(item)
    elif isinstance(node, dict):
        block_type = node.get("type")
        value = node.get("value")
        if (
            block_type in TEXT_SOURCE_FIELD
            and isinstance(value, dict)
            # Idempotency guard, same as 0045: the source field is always
            # present pre-migration (Wagtail serializes every declared child
            # block) and always absent post-migration.
            and TEXT_SOURCE_FIELD[block_type] in value
        ):
            _combine(block_type, value)
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
        ("wtrx", "0046_alter_contentpage_body_alter_homepage_body_and_more"),
    ]

    operations = [
        # Not cleanly reversible -- same reasoning as 0045.
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

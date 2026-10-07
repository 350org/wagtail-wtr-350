# SignupActionKitBlock's "content" field (heading+description, added in
# 0047_condense_more_heading_text_blocks) is dropped for the hero's inline
# CTA strip -- HeroCTABlock's "signup" choice is now HeroSignupActionKitBlock,
# a separate block class with no content field at all (see its docstring in
# wtrx/blocks/__init__.py: the hero's compact rendering never used it, and
# every existing hero CTA signup panel already had it blank).
#
# Verified against every current hero_cta "signup" entry before writing this
# migration: content was empty on both (HomePage 3 and 51), so this drops an
# always-empty key -- not a lossy content migration like 0045/0047. Still
# walks revisions too, for the same reason those did: an old revision could
# in principle carry a non-empty value, and reverting to one would otherwise
# bring back a key the block no longer declares.
import json

from django.db import migrations


def _drop_content(node):
    """Walk parsed StreamField JSON, dropping "content" from "signup"-typed
    blocks in place. Returns True if anything changed."""
    changed = False
    if isinstance(node, list):
        for item in node:
            changed |= _drop_content(item)
    elif isinstance(node, dict):
        value = node.get("value")
        if node.get("type") == "signup" and isinstance(value, dict) and "content" in value:
            del value["content"]
            changed = True
        for child in node.values():
            if isinstance(child, (list, dict)):
                changed |= _drop_content(child)
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
                if _drop_content(raw):
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
                if _drop_content(parsed):
                    content[name] = json.dumps(parsed)
                    dirty = True
            if dirty:
                revision.content = content
                revision.save(update_fields=["content"])


class Migration(migrations.Migration):
    dependencies = [
        ("wtrx", "0048_alter_blogs_hero_cta_alter_contentpage_body_and_more"),
    ]

    operations = [
        # Not reversible: the dropped value is discarded, not archived.
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

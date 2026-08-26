# Rewrites the pre-palette background keys that individual blocks used to
# carry onto the shared BACKGROUND_COLOR_CHOICES keys.
#
# Before this, five blocks each named the same handful of fills differently:
# SectionBlock offered light/dark/primary/secondary/muted built out of raw
# Tailwind utilities, FeaturePanelBlock only light/dark, SignupActionKitBlock
# spelled dark grey "dark" while CalloutBlock and the hero banner spelled it
# "dark-grey". They now share one list, so the stored values have to be
# brought onto it too.
#
# This is deliberately not the only place the mapping lives — see
# LEGACY_BACKGROUND_VALUES and resolve_background() in wtrx/blocks/__init__.py,
# which the render path still goes through. A page revision saved before this
# migration keeps its own copy of the block JSON, and reverting to one
# re-publishes that JSON verbatim, so a legacy key can reappear at any time
# and the runtime fallback has to stay.
import json

from django.db import migrations

# Which key holds the background on each block type that has one. `hero` is
# the mid-page HeroBlock; the page-level HeroMixin equivalent is the
# hero_banner_color CharField, whose stored values were already canonical and
# so need no rewriting here.
BACKGROUND_FIELDS = {
    "section": "background",
    "callout": "color",
    "feature_panel": "background",
    "signup_actionkit": "background",
    "hero": "banner_color",
}

# Must stay in step with LEGACY_BACKGROUND_VALUES in wtrx/blocks/__init__.py.
# Duplicated rather than imported because a migration has to keep working
# against the code as it was when the migration was written, not as it is now.
LEGACY_VALUES = {
    "light": "white",
    "dark": "dark-grey",
    "muted": "light-grey",
    "primary": "blue-gradient",
    "secondary": "navy",
}


def _rewrite(node, mapping):
    """
    Walk parsed StreamField JSON, rewriting legacy background values in place.

    Returns True if anything changed. Blocks nest arbitrarily (a section holds
    content, a card grid holds cards, and a section can hold a callout), so
    this recurses through every list and dict rather than knowing the shape.
    """
    changed = False
    if isinstance(node, list):
        for item in node:
            changed |= _rewrite(item, mapping)
    elif isinstance(node, dict):
        field = BACKGROUND_FIELDS.get(node.get("type"))
        value = node.get("value")
        if field and isinstance(value, dict) and value.get(field) in mapping:
            value[field] = mapping[value[field]]
            changed = True
        for child in node.values():
            if isinstance(child, (list, dict)):
                changed |= _rewrite(child, mapping)
    return changed


def _stream_field_names(model):
    from wagtail.fields import StreamField

    return [f.name for f in model._meta.get_fields() if isinstance(f, StreamField)]


def _migrate(apps, mapping):
    Revision = apps.get_model("wagtailcore", "Revision")
    ContentType = apps.get_model("contenttypes", "ContentType")

    content_type_ids = []
    # apps.get_app_config("wtrx").get_models() comes back empty against the
    # migration state's AppConfigStub; get_models() on the state itself does not.
    for model in [m for m in apps.get_models() if m._meta.app_label == "wtrx"]:
        field_names = _stream_field_names(model)
        if not field_names:
            continue

        for obj in model.objects.all().iterator():
            dirty = False
            for name in field_names:
                # list() is load-bearing: StreamValue.raw_data is a lazy
                # RawDataView, not a list, so _rewrite would not recognise it
                # as a sequence and would walk nothing at all.
                raw = list(getattr(obj, name).raw_data)
                if _rewrite(raw, mapping):
                    setattr(obj, name, json.dumps(raw))
                    dirty = True
            if dirty:
                obj.save(update_fields=field_names)

        # Revisions hold their own copy of the same JSON, and reverting to one
        # republishes it — so an unmigrated revision would quietly undo this.
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
                if _rewrite(parsed, mapping):
                    content[name] = json.dumps(parsed)
                    dirty = True
            if dirty:
                revision.content = content
                revision.save(update_fields=["content"])


def forwards(apps, schema_editor):
    _migrate(apps, LEGACY_VALUES)


def backwards(apps, schema_editor):
    # Not a clean inverse: "light" and "muted" both mapped onto fills that
    # White and Light grey now share with values that were never legacy, so
    # reversing sends every white section back to "light" and every light-grey
    # one to "muted" regardless of which it started as. Good enough to let the
    # migration be unapplied; the colours it produces are the same ones.
    reverse = {"white": "light", "dark-grey": "dark", "light-grey": "muted"}
    _migrate(apps, reverse)


class Migration(migrations.Migration):
    dependencies = [
        ("wtrx", "0039_alter_blogs_hero_banner_color_alter_blogs_hero_cta_and_more"),
        ("wagtailcore", "0089_log_entry_data_json_null_to_object"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

# Deletes every `hero` block (the removed mid-page HeroBlock) from page
# bodies and their revisions.
#
# 0101 took `hero` out of BodyStreamBlock and SectionContentBlock (and so out
# of TimelineYearContentBlock, which subclasses it). A hero now only ever
# comes from the page's own hero fields (HeroMixin / BannerHeroMixin).
# Wagtail already skips a stored block whose type is no longer registered, so
# without this the blocks would vanish from the page anyway and be dropped on
# the next save; this makes that explicit, and covers revisions, which hold
# their own copy of the JSON and would otherwise bring the blocks back on a
# revert. Each removal is printed so a deploy log says what was deleted.
#
# Unapplying it is a no-op: the deleted content is not kept anywhere.
import json

from django.db import migrations

REMOVED_TYPE = "hero"


def _strip(node):
    """
    Remove every {"type": "hero", ...} entry from parsed StreamField JSON, in
    place, at any depth (a section's content, a timeline year's content).
    Returns the number removed.
    """
    removed = 0
    if isinstance(node, list):
        kept = [item for item in node if not (isinstance(item, dict) and item.get("type") == REMOVED_TYPE)]
        removed += len(node) - len(kept)
        node[:] = kept
        for item in node:
            removed += _strip(item)
    elif isinstance(node, dict):
        for child in node.values():
            if isinstance(child, (list, dict)):
                removed += _strip(child)
    return removed


def _stream_field_names(model):
    from wagtail.fields import StreamField

    return [f.name for f in model._meta.get_fields() if isinstance(f, StreamField)]


def forwards(apps, schema_editor):
    Revision = apps.get_model("wagtailcore", "Revision")
    ContentType = apps.get_model("contenttypes", "ContentType")
    connection = schema_editor.connection
    qn = connection.ops.quote_name

    for model in [m for m in apps.get_models() if m._meta.app_label == "wtrx"]:
        field_names = _stream_field_names(model)
        if not field_names:
            continue

        # Read with raw SQL, not the ORM: by now 0101 has unregistered `hero`, and
        # StreamValue.raw_data silently omits a block whose type the field no
        # longer knows -- reading through the model would find nothing to
        # strip and leave the stored JSON untouched.
        table = qn(model._meta.db_table)
        pk_column = qn(model._meta.pk.column)
        for name in field_names:
            column = qn(model._meta.get_field(name).column)
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT {pk_column}, {column} FROM {table}")
                rows = cursor.fetchall()
            for pk, stored in rows:
                if not isinstance(stored, str):
                    # PostgreSQL jsonb comes back already parsed.
                    stored = json.dumps(stored)
                if f'"{REMOVED_TYPE}"' not in stored:
                    continue
                parsed = json.loads(stored)
                removed = _strip(parsed)
                if removed:
                    print(f"\n  {model.__name__} {pk} {name}: removed {removed} hero block(s)", end="")
                    # Writing back through the ORM is safe: every block
                    # left in `parsed` is still registered.
                    model.objects.filter(pk=pk).update(**{name: json.dumps(parsed)})

        ct = ContentType.objects.filter(app_label="wtrx", model=model._meta.model_name).first()
        if ct is None:
            continue
        for revision in Revision.objects.filter(content_type_id=ct.pk).iterator():
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
                if _strip(parsed):
                    content[name] = json.dumps(parsed)
                    dirty = True
            if dirty:
                revision.content = content
                revision.save(update_fields=["content"])


class Migration(migrations.Migration):
    dependencies = [
        ("wtrx", "0101_remove_hero_body_block"),
        ("wagtailcore", "0089_log_entry_data_json_null_to_object"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

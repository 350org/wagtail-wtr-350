from django.db import migrations
from django.utils.html import escape

MODELS = ["HomePage", "ContentPage", "IndexPage", "Blogs", "Post"]


def as_rich_text(text):
    """Wrap a plain-text headline as one paragraph; leave rich text alone."""
    if not text or text.lstrip().startswith("<"):
        return text
    return f"<p>{escape(text)}</p>"


def forwards(apps, schema_editor):
    for model_name in MODELS:
        Model = apps.get_model("wtrx", model_name)
        for page in Model.objects.exclude(hero_headline="").only("pk", "hero_headline"):
            converted = as_rich_text(page.hero_headline)
            if converted != page.hero_headline:
                Model.objects.filter(pk=page.pk).update(hero_headline=converted)

    # Revisions carry their own copy of the field; convert them too so a
    # revert or a draft opens with the same markup as the live page.
    Revision = apps.get_model("wagtailcore", "Revision")
    for revision in Revision.objects.filter(content__has_key="hero_headline").exclude(content__hero_headline=""):
        converted = as_rich_text(revision.content["hero_headline"])
        if converted != revision.content["hero_headline"]:
            revision.content["hero_headline"] = converted
            Revision.objects.filter(pk=revision.pk).update(content=revision.content)


class Migration(migrations.Migration):

    dependencies = [
        ("wtrx", "0089_hero_headline_rich_text"),
        ("wagtailcore", "0001_initial"),
    ]

    operations = [
        # Not reversed: headline_html() renders both shapes, so the rich text
        # can stay in place if the schema change is rolled back.
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

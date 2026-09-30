from django.db import migrations

# English category name -> {language code: label}. Matched case-insensitively,
# since the category names were created by the importers ("Climate Finance").
LABELS = {
    "climate finance": {"fr-fr": "Finance climat", "pt-br": "Financiamento climático", "id": "Pendanaan iklim"},
    "climate impacts": {"fr-fr": "Impacts climatiques", "pt-br": "Impactos climáticos", "id": "Dampak iklim"},
    "climate justice": {"fr-fr": "Justice climatique", "pt-br": "Justiça climática", "id": "Keadilan iklim"},
    "renewable energy": {
        "fr-fr": "Énergies renouvelables",
        "pt-br": "Energia renovável",
        "id": "Energi terbarukan",
    },
    "fossil fuels": {"fr-fr": "Énergies fossiles", "pt-br": "Combustíveis fósseis", "id": "Bahan bakar fosil"},
}


def seed_labels(apps, schema_editor):
    BlogCategory = apps.get_model("wtrx", "BlogCategory")
    BlogCategoryLabel = apps.get_model("wtrx", "BlogCategoryLabel")
    Locale = apps.get_model("wagtailcore", "Locale")

    locales = {locale.language_code: locale for locale in Locale.objects.all()}
    for category in BlogCategory.objects.all():
        for language_code, name in LABELS.get(category.name.lower(), {}).items():
            locale = locales.get(language_code)
            if locale is None:
                continue
            BlogCategoryLabel.objects.get_or_create(category=category, locale=locale, defaults={"name": name})


class Migration(migrations.Migration):

    dependencies = [
        ("wtrx", "0087_blog_category_labels"),
        ("wagtailcore", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_labels, migrations.RunPython.noop),
    ]

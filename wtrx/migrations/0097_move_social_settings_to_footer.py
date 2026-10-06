"""
Copy each site's Settings > Social row onto its Settings > Footer row.

Social links and their two display toggles now live on FooterSettings, so
that a footer override can carry its own social links for a country site
(see FooterSettings.social_for_page()). SocialSettings itself is deleted by
the next migration, so without this copy every site would lose its social
icons, and its twitter:site meta tag, on deploy.

A site with a SocialSettings row but no FooterSettings row gets one
created, since it would otherwise fall back to the field defaults (no
links). Reversible: the reverse copies the same three values back.
"""

from django.db import migrations


def copy_social_to_footer(apps, schema_editor):
    SocialSettings = apps.get_model("wtrx", "SocialSettings")
    FooterSettings = apps.get_model("wtrx", "FooterSettings")
    for social in SocialSettings.objects.all():
        footer, _ = FooterSettings.objects.get_or_create(site_id=social.site_id)
        footer.social_links = list(social.social_links.raw_data)
        footer.show_social_in_header = social.show_in_header
        footer.show_social_in_footer = social.show_in_footer
        footer.save()


def copy_footer_to_social(apps, schema_editor):
    SocialSettings = apps.get_model("wtrx", "SocialSettings")
    FooterSettings = apps.get_model("wtrx", "FooterSettings")
    for footer in FooterSettings.objects.all():
        social, _ = SocialSettings.objects.get_or_create(site_id=footer.site_id)
        social.social_links = list(footer.social_links.raw_data)
        social.show_in_header = footer.show_social_in_header
        social.show_in_footer = footer.show_social_in_footer
        social.save()


class Migration(migrations.Migration):

    dependencies = [
        ("wtrx", "0096_footer_social_links"),
    ]

    operations = [
        migrations.RunPython(copy_social_to_footer, copy_footer_to_social),
    ]

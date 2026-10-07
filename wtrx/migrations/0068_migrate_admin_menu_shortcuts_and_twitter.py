from django.db import migrations


def migrate_admin_menu_shortcuts_and_twitter(apps, schema_editor):
    """
    Move data out of the two fields the next migration removes, before it
    removes them:

    - AdminMenuSettings.blog_index_page / press_releases_index_page (each a
      nullable FK) -> one AdminSidebarShortcutBlock entry each in the new
      sidebar_shortcuts StreamField, added by the previous migration. See
      AdminSidebarShortcutBlock's own docstring (wtrx/site_settings.py).
    - BrandingSEOSettings.twitter_site (an "@handle" CharField) -> a
      SocialLinkBlock entry (platform="twitter") in that site's
      SocialSettings.social_links, in the URL form SocialSettings.twitter_handle
      parses back out of (see that property's docstring).
    """
    AdminMenuSettings = apps.get_model("wtrx", "AdminMenuSettings")
    BrandingSEOSettings = apps.get_model("wtrx", "BrandingSEOSettings")
    SocialSettings = apps.get_model("wtrx", "SocialSettings")

    for admin_menu in AdminMenuSettings.objects.all():
        shortcuts = list(admin_menu.sidebar_shortcuts.raw_data)
        changed = False
        if admin_menu.blog_index_page_id:
            shortcuts.append(
                {
                    "type": "shortcut",
                    "value": {
                        "label": "Blog",
                        "page": admin_menu.blog_index_page_id,
                        "icon": "",
                    },
                }
            )
            changed = True
        if admin_menu.press_releases_index_page_id:
            shortcuts.append(
                {
                    "type": "shortcut",
                    "value": {
                        "label": "Press releases",
                        "page": admin_menu.press_releases_index_page_id,
                        "icon": "",
                    },
                }
            )
            changed = True
        if changed:
            admin_menu.sidebar_shortcuts = shortcuts
            admin_menu.save(update_fields=["sidebar_shortcuts"])

    for branding in BrandingSEOSettings.objects.all():
        handle = (branding.twitter_site or "").strip().lstrip("@")
        if not handle:
            continue
        social, _created = SocialSettings.objects.get_or_create(site_id=branding.site_id)
        links = list(social.social_links.raw_data)
        if any(link.get("value", {}).get("platform") == "twitter" for link in links):
            continue
        links.append(
            {
                "type": "link",
                "value": {"platform": "twitter", "url": f"https://twitter.com/{handle}"},
            }
        )
        social.social_links = links
        social.save(update_fields=["social_links"])


def noop_reverse(apps, schema_editor):
    """
    Not reversible: the fields this populates (sidebar_shortcuts,
    social_links) may carry other, unrelated entries by the time a reverse
    migration runs, so there's no way to tell which entries came from this
    step. Reversing is a no-op -- the old fields removed by the next
    migration would need re-adding first anyway.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("wtrx", "0067_adminmenusettings_sidebar_shortcuts_and_more"),
    ]

    operations = [
        migrations.RunPython(migrate_admin_menu_shortcuts_and_twitter, noop_reverse),
    ]

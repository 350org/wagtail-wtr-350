"""
Hand-written (not via `makemigrations`).

`makemigrations`'s autodetector (and even plain `migrate`, which needs to
render historical ProjectState for the pre_migrate signal) crashes trying to
deconstruct old StreamField definitions: HomePage/ContentPage/IndexPage's
`body` field history contained a PageCardsBlock whose `page_type` included
"wtrx.BlogIndexPage"/"wtrx.PressReleaseIndexPage" as strings, frozen into
migration 0025's serialized block_lookup. Deconstructing that block calls
Wagtail's resolve_model_string(), which resolves against the *live* app
registry (not a historical snapshot) -- so once those classes are renamed/
removed from models.py, rendering ANY historical state that includes them
raises a LookupError, even for migrations that have nothing to do with this
rename. Fixed by editing migration 0025's frozen string literals directly
(safe: already-applied migrations are never re-executed, only re-parsed for
state-rendering, so editing them doesn't touch already-applied SQL) -- see
that file's `page_type` values, now 'wtrx.Blogs' instead of the old pair.

With that fixed, this migration is a plain, self-contained rename/merge.
"""

import modelcluster.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('wtrx', '0026_blogpage_author_name_blogpage_author_title'),
    ]

    operations = [
        migrations.RenameModel(old_name='BlogPage', new_name='Post'),
        migrations.RenameModel(old_name='BlogIndexPage', new_name='Blogs'),
        migrations.AlterModelOptions(
            name='post',
            options={'verbose_name': 'post', 'verbose_name_plural': 'posts'},
        ),
        migrations.AlterModelOptions(
            name='blogs',
            options={'verbose_name': 'Blogs', 'verbose_name_plural': 'Blogs'},
        ),
        migrations.AlterField(
            model_name='post',
            name='categories',
            field=modelcluster.fields.ParentalManyToManyField(
                blank=True, related_name='posts', to='wtrx.blogcategory', verbose_name='categories'
            ),
        ),
        migrations.DeleteModel(name='PressReleasePage'),
        migrations.DeleteModel(name='PressReleaseIndexPage'),
    ]

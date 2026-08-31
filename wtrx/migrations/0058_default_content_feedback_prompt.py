"""
Backfill wagtail_ai.AgentSettings.content_feedback_prompt for any row saved
before wtrx.ai.patch_content_feedback_prompt_default() gave that field a
default. A Django field default only applies to newly-constructed instances
-- it never retroactively updates a row that was already saved with an
empty string, so this repo's own AgentSettings row (and any other
already-provisioned site's) needs a one-time backfill in addition to the
runtime patch. See wtrx/ai.py and AGENTS.md rule #11's "Get content
feedback" bullet for why a blank prompt breaks the "Get content feedback"
button.

The default text is hardcoded here (rather than imported from wtrx.ai) on
purpose: a data migration's behaviour should stay frozen at the point it
was written, not silently change if wtrx.ai.DEFAULT_CONTENT_FEEDBACK_PROMPT
is edited later. Keep this in sync with that constant if it changes.
"""

from django.db import migrations

DEFAULT_CONTENT_FEEDBACK_PROMPT = (
    "Review this page's content as an experienced editor for a nonprofit "
    "or advocacy organization's public website. Focus on: clarity and "
    "readability for a general public audience; whether the tone matches "
    "the organization's mission and voice; whether calls to action are "
    "clear, compelling, and easy to find; inclusive and accessible "
    "language; and anything likely to reduce visitor trust or engagement. "
    "Comment on the substance of the writing, not on formatting or markup."
)


def backfill_content_feedback_prompt(apps, schema_editor):
    AgentSettings = apps.get_model("wagtail_ai", "AgentSettings")
    AgentSettings.objects.filter(content_feedback_prompt="").update(
        content_feedback_prompt=DEFAULT_CONTENT_FEEDBACK_PROMPT
    )


def noop_reverse(apps, schema_editor):
    """Not reversible: we can't tell a backfilled default from one an editor
    genuinely typed themselves, so reversing would risk blanking real
    content. Leaving rows as-is on a reverse migration is the safe choice."""


class Migration(migrations.Migration):

    dependencies = [
        ("wtrx", "0057_remove_blogs_hero_layout_and_more"),
        ("wagtail_ai", "0003_agentsettings"),
    ]

    operations = [
        migrations.RunPython(backfill_content_feedback_prompt, noop_reverse),
    ]

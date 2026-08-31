"""
Patch around a wagtail-ai upstream gap: AgentSettings.content_feedback_prompt
ships with no default, unlike every sibling prompt field on
AgentSettingsMixin (see AGENTS.md rule #11's "Get content feedback" bullet).

Left blank, ContentFeedbackAgent.execute() builds a `messages` list that is
entirely role="system" -- Anthropic's API extracts every system-role entry
out of `messages` and requires at least one non-system message left over, so
every "Get content feedback" click failed with "messages: at least one
message is required".

Called from WtrxConfig.ready().
"""

from django.db.models.signals import post_init

from wagtail_ai.agents.content_feedback import ContentFeedbackAgent
from wagtail_ai.models import AgentSettings

# Kept in sync with wtrx/migrations/0056_default_content_feedback_prompt.py,
# which backfills existing AgentSettings rows saved before this default
# existed (a default only applies to newly-constructed instances -- it never
# retroactively updates an already-saved row). The migration hardcodes its
# own copy on purpose -- see that file's docstring.
DEFAULT_CONTENT_FEEDBACK_PROMPT = (
    "Review this page's content as an experienced editor for a nonprofit "
    "or advocacy organization's public website. Focus on: clarity and "
    "readability for a general public audience; whether the tone matches "
    "the organization's mission and voice; whether calls to action are "
    "clear, compelling, and easy to find; inclusive and accessible "
    "language; and anything likely to reduce visitor trust or engagement. "
    "Comment on the substance of the writing, not on formatting or markup."
)


def default_content_feedback_prompt():
    """Default value for AgentSettings.content_feedback_prompt."""
    return DEFAULT_CONTENT_FEEDBACK_PROMPT


def _apply_content_feedback_prompt_default(sender, instance, **kwargs):
    """
    post_init handler standing in for a real field-level `default=` on
    AgentSettings.content_feedback_prompt.

    We deliberately do NOT set `field.default` directly on the third-party
    model: that mutates a Field object that Django's migration autodetector
    inspects, and since wagtail-ai's own migrations live in site-packages
    (outside this repo), doing so makes `makemigrations` perpetually want to
    generate an "AlterField" migration for the `wagtail_ai` app that we have
    nowhere appropriate to commit -- breaking `makemigrations --check`.

    `instance.pk is None` is True only for a freshly-constructed, not-yet-
    saved instance (e.g. `AgentSettings()`, including the first row a brand
    new site creates via `AgentSettings.load()`'s `objects.create()` call)
    and False for an instance loaded from an existing row -- exactly the
    condition under which a real field default would apply. Note
    `instance._state.adding` is NOT a reliable signal here: Django's
    `from_db()` constructs the instance via the normal `__init__()` (so this
    post_init handler still fires) and only flips `_state.adding` to False
    *after* `__init__()` returns -- by which point this handler has already
    run, so `_state.adding` reads True even for a row loaded from the
    database.
    """
    if instance.pk is None and not instance.content_feedback_prompt:
        instance.content_feedback_prompt = default_content_feedback_prompt()


def _get_prompt_messages_with_fallback(self, settings):
    """
    Defensive replacement for ContentFeedbackAgent._get_prompt_messages():
    always emit at least one non-system message, even if
    content_feedback_prompt is somehow blank (e.g. an editor clears it and
    saves, or it's set via a raw .update() that bypasses the above). Degrades
    gracefully to the same default text rather than silently sending an
    all-system `messages` list to the API.
    """
    prompt = settings.content_feedback_prompt or default_content_feedback_prompt()
    return [{"role": "user", "content": prompt}]


def patch_content_feedback_prompt_default():
    """
    Give AgentSettings.content_feedback_prompt the default it's missing, and
    make ContentFeedbackAgent degrade gracefully if it's ever blank anyway.
    See module docstring.
    """
    post_init.connect(
        _apply_content_feedback_prompt_default,
        sender=AgentSettings,
        dispatch_uid="wtrx_agent_settings_content_feedback_prompt_default",
    )
    ContentFeedbackAgent._get_prompt_messages = _get_prompt_messages_with_fallback

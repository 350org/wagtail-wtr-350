"""
Tests for wtrx/ai.py -- the fix for AgentSettings.content_feedback_prompt
shipping with no default (see AGENTS.md rule #11's "Get content feedback"
bullet, and wtrx/ai.py's module docstring).

Without this fix, a blank content_feedback_prompt made
ContentFeedbackAgent._get_prompt_messages() return an empty list, which in
turn made ContentFeedbackAgent.execute() send Anthropic's API a `messages`
list that was entirely role="system" -- rejected with "messages: at least
one message is required" since Anthropic extracts every system-role entry
out of `messages` and requires at least one non-system message left over.
"""

from django.test import TestCase

from wagtail_ai.agents.content_feedback import ContentFeedbackAgent
from wagtail_ai.models import AgentSettings

from wtrx.ai import DEFAULT_CONTENT_FEEDBACK_PROMPT


class TestAgentSettingsContentFeedbackPromptDefault(TestCase):
    def test_fresh_agent_settings_has_non_empty_content_feedback_prompt(self):
        """A brand new, unsaved AgentSettings (what a fresh site's first
        Settings > Agents row starts as) must not have a blank
        content_feedback_prompt -- see wtrx.ai.patch_content_feedback_prompt_default."""
        settings = AgentSettings()
        self.assertTrue(settings.content_feedback_prompt)
        self.assertEqual(
            settings.content_feedback_prompt, DEFAULT_CONTENT_FEEDBACK_PROMPT
        )

    def test_explicit_value_is_not_overridden(self):
        """The default only fills in a blank value -- it must never clobber
        a value an editor actually set."""
        settings = AgentSettings(content_feedback_prompt="Custom instructions.")
        self.assertEqual(settings.content_feedback_prompt, "Custom instructions.")

    def test_loading_an_existing_blank_row_is_not_overridden_in_memory(self):
        """Loading an existing (already-saved) row with a blank prompt must
        not silently rewrite it in memory -- only a genuinely new instance
        gets the default. Persisted blank rows are handled by the
        0056_default_content_feedback_prompt data migration instead.

        Uses a queryset .update() (bypassing __init__/post_init, unlike
        .save()) to simulate a row saved blank before this fix existed --
        .create(content_feedback_prompt="") would otherwise have the
        default filled in before the INSERT even happens."""
        saved = AgentSettings.objects.create()
        AgentSettings.objects.filter(pk=saved.pk).update(content_feedback_prompt="")
        reloaded = AgentSettings.objects.get(pk=saved.pk)
        self.assertEqual(reloaded.content_feedback_prompt, "")


class TestContentFeedbackAgentPromptMessagesFallback(TestCase):
    def test_never_returns_an_empty_message_list(self):
        """_get_prompt_messages() must always return at least one message,
        even if content_feedback_prompt is blank on the settings object
        passed in (e.g. an existing row saved before this fix, or one set
        blank via a raw .update())."""
        settings = AgentSettings(content_feedback_prompt="")
        messages = ContentFeedbackAgent()._get_prompt_messages(settings)
        self.assertGreaterEqual(len(messages), 1)

    def test_fallback_messages_are_not_all_system_role(self):
        """Anthropic's API extracts every role="system" message out of
        `messages` and requires at least one non-system message left over --
        the exact failure this fix addresses."""
        settings = AgentSettings(content_feedback_prompt="")
        messages = ContentFeedbackAgent()._get_prompt_messages(settings)
        self.assertTrue(any(m["role"] != "system" for m in messages))

    def test_uses_the_configured_prompt_when_set(self):
        settings = AgentSettings(content_feedback_prompt="Custom instructions.")
        messages = ContentFeedbackAgent()._get_prompt_messages(settings)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["content"], "Custom instructions.")

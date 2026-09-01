"""
Tests for the backfill_image_descriptions management command (see
wtrx/management/commands/backfill_image_descriptions.py).

BasicPromptAgent.execute is mocked throughout -- these tests must never make
a real LLM call. They pin: generation is cached to disk without touching the
database unless --apply is passed, a cached entry is never regenerated, a
failure on one image doesn't stop the rest, and only images with a blank
description are ever considered.
"""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import TestCase

from wagtail.images.tests.utils import get_test_image_file

from wtrx.images import CustomImage


class BackfillImageDescriptionsTest(TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.cache_path = Path(tmpdir.name) / "cache.json"

    def _image(self, title="filename_title", description=""):
        return CustomImage.objects.create(
            title=title,
            description=description,
            file=get_test_image_file(size=(1200, 800)),
        )

    def _run(self, execute_return="A generated description.", execute_side_effect=None, **kwargs):
        out = StringIO()
        with patch(
            "wagtail_ai.agents.basic_prompt.BasicPromptAgent.execute",
            return_value=execute_return,
            side_effect=execute_side_effect,
        ) as mock_execute:
            call_command(
                "backfill_image_descriptions",
                cache_file=str(self.cache_path),
                stdout=out,
                **kwargs,
            )
        return out.getvalue(), mock_execute

    def _cache(self):
        if not self.cache_path.exists():
            return {}
        return json.loads(self.cache_path.read_text())

    def test_generates_and_caches_without_writing_to_the_database(self):
        image = self._image()

        self._run(execute_return="A vivid description.")

        image.refresh_from_db()
        self.assertEqual(image.description, "")
        self.assertEqual(self._cache()[str(image.pk)]["description"], "A vivid description.")

    def test_apply_writes_the_cached_description(self):
        image = self._image()

        self._run(execute_return="A vivid description.", apply=True)

        image.refresh_from_db()
        self.assertEqual(image.description, "A vivid description.")

    def test_apply_reuses_an_existing_cache_entry_without_regenerating(self):
        image = self._image()
        self._run(execute_return="First pass.")

        _, mock_execute = self._run(
            execute_return="Would be a second pass.", apply=True
        )

        mock_execute.assert_not_called()
        image.refresh_from_db()
        self.assertEqual(image.description, "First pass.")

    def test_images_with_an_existing_description_are_never_touched(self):
        self._image(description="Already described.")

        _, mock_execute = self._run()

        mock_execute.assert_not_called()
        self.assertEqual(self._cache(), {})

    def test_limit_caps_how_many_new_generations_happen(self):
        self._image(title="one")
        self._image(title="two")

        self._run(execute_return="Generated.", limit=1)

        self.assertEqual(len(self._cache()), 1)

    def test_a_failure_on_one_image_does_not_stop_the_batch(self):
        first = self._image(title="broken")
        second = self._image(title="fine")

        out = StringIO()
        with patch(
            "wagtail_ai.agents.basic_prompt.BasicPromptAgent.execute",
            side_effect=[ValidationError("boom"), "A fine description."],
        ):
            call_command(
                "backfill_image_descriptions",
                cache_file=str(self.cache_path),
                stdout=out,
                stderr=out,
            )

        cache = self._cache()
        self.assertNotIn(str(first.pk), cache)
        self.assertEqual(cache[str(second.pk)]["description"], "A fine description.")

    def test_image_id_filters_to_a_single_image(self):
        wanted = self._image(title="wanted")
        self._image(title="not wanted")

        self._run(execute_return="Generated.", image_id=wanted.pk)

        self.assertEqual(list(self._cache().keys()), [str(wanted.pk)])

    def test_raises_when_no_prompt_is_configured(self):
        # Patch the name as imported into the command module (AGENTS.md #24)
        # -- not wagtail_ai.agents.base, whose reference the command doesn't use.
        with patch(
            "wtrx.management.commands.backfill_image_descriptions.get_agent_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value.image_description_prompt = ""
            with self.assertRaises(CommandError):
                call_command(
                    "backfill_image_descriptions", cache_file=str(self.cache_path)
                )

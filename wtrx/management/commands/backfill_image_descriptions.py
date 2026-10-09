"""
Bulk-generate descriptions for CustomImage rows that predate the requirement
that every image have one (see wtrx/images.py -- description is now
blank=False, since it's what alt text is derived from; a blank one falls
back to a filename-derived title).

Reuses the exact same generation path the "Generate description" wand button
already uses in the Images admin -- wagtail_ai's BasicPromptAgent, driven by
the Settings > Agents "Image description" prompt -- rather than
reimplementing prompt/LLM logic.

Without --apply, results are only cached to a JSON file, so a review pass
never has to re-pay for the same LLM call: inspect or hand-edit the cache,
then pass --apply later to write cached descriptions without regenerating.
With --apply, each description is saved to the database as soon as it is
generated, so an interrupted run loses at most the call in flight.

    python manage.py backfill_image_descriptions --limit 5           # generate + cache only
    python manage.py backfill_image_descriptions --limit 5 --apply   # generate/reuse cache, then save
    python manage.py backfill_image_descriptions --apply             # apply everything already cached
    python manage.py backfill_image_descriptions --image-id 42 --apply
    python manage.py backfill_image_descriptions --limit 20 --newest-first --apply

Idempotent: only ever targets images whose description is still blank, so
partial runs (--limit, Ctrl-C, a restart, an API failure) are always safe to
re-run. SVGs are skipped: the model only accepts JPEG, PNG, GIF and WebP,
and an SVG's rendition is still an SVG. On PostgreSQL only one run proceeds at a time; a second exits
immediately rather than paying for the same images twice.
"""

import json
from contextlib import contextmanager
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from anthropic import BadRequestError
from any_llm.exceptions import AnyLLMError
from wagtail_ai.agents.base import get_agent_settings
from wagtail_ai.agents.basic_prompt import BasicPromptAgent

from wtrx.images import CustomImage

DEFAULT_CACHE_FILE = "image_description_backfill_cache.json"
DEFAULT_MAX_CONSECUTIVE_FAILURES = 5
# Arbitrary key for pg_try_advisory_lock; only has to be unique to this command.
ADVISORY_LOCK_ID = 7_350_001


def fit_description(description: str, max_length: int) -> str:
    """Shorten an over-long generated description to fit the field.

    The prompt asks for at most max_length characters but the model can run
    over, which would fail the save. Prefer ending on the last full sentence
    when that keeps at least half the limit; otherwise cut at a word boundary
    and mark the cut with an ellipsis.
    """
    description = description.strip()
    if len(description) <= max_length:
        return description
    head = description[:max_length]
    sentence_end = max(head.rfind(". "), head.rfind("! "), head.rfind("? "))
    if sentence_end >= max_length // 2:
        return head[:sentence_end + 1]
    words = description[:max_length - 1].rsplit(" ", 1)[0]
    return words.rstrip(" ,;:-") + "\u2026"


class Command(BaseCommand):
    help = "Generate (and optionally apply) AI descriptions for images missing one."

    def add_arguments(self, parser):
        parser.add_argument(
            "--cache-file",
            default=DEFAULT_CACHE_FILE,
            help="JSON file to read/write generated descriptions (default: %s)." % DEFAULT_CACHE_FILE,
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Only generate for at most N images lacking a cache entry (does not limit --apply).",
        )
        parser.add_argument(
            "--image-id",
            type=int,
            default=None,
            help="Only process this single image ID.",
        )
        parser.add_argument(
            "--newest-first",
            action="store_true",
            help="Process the most recently uploaded images first (default: oldest first).",
        )
        parser.add_argument(
            "--max-consecutive-failures",
            type=int,
            default=DEFAULT_MAX_CONSECUTIVE_FAILURES,
            help="Abort after this many generations fail in a row (default: %d)." % DEFAULT_MAX_CONSECUTIVE_FAILURES,
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Save each description to the database. Without this, only the cache file is populated.",
        )

    def handle(self, *args, **options):
        with self._single_run_lock() as acquired:
            if not acquired:
                self.stdout.write("Another backfill_image_descriptions run is in progress; exiting.")
                return
            self._run(options)

    def _run(self, options):
        cache_path = Path(options["cache_file"])
        cache = self._load_cache(cache_path)

        images = CustomImage.objects.filter(description="").order_by(
            "-created_at" if options["newest_first"] else "pk"
        )
        if options["image_id"] is not None:
            images = images.filter(pk=options["image_id"])

        prompt_text = get_agent_settings().image_description_prompt
        if not prompt_text:
            raise CommandError(
                "AgentSettings.image_description_prompt is empty -- set it under "
                "Settings > Agents in the admin before running this command."
            )
        max_length = CustomImage._meta.get_field("description").max_length
        agent = BasicPromptAgent()

        generated = applied = failures_in_a_row = 0
        stopped_early = False
        for pk in list(images.values_list("pk", flat=True)):
            key = str(pk)
            entry = cache.get(key)
            if entry is None and options["limit"] is not None and generated >= options["limit"]:
                stopped_early = True
                continue
            # Re-read each row: a long run must not overwrite a description an
            # editor (or a concurrent run) filled in after the list was taken.
            image = CustomImage.objects.filter(pk=pk, description="").first()
            if image is None:
                continue
            if entry is None and image.is_svg():
                self.stdout.write("SKIPPED %5s %-40s -> SVG, write its description by hand" % (pk, image.title[:40]))
                continue
            if entry is None:
                description = self._generate(agent, prompt_text, max_length, image)
                generated += 1
                if description is None:
                    failures_in_a_row += 1
                    if failures_in_a_row >= options["max_consecutive_failures"]:
                        raise CommandError(
                            "Aborting after %d consecutive failures (see FAILED lines above)." % failures_in_a_row
                        )
                    continue
                failures_in_a_row = 0
                if len(description) > max_length:
                    self.stdout.write("TRIMMED %5s from %d characters" % (pk, len(description)))
                    description = fit_description(description, max_length)
                entry = {"title": image.title, "description": description}
                cache[key] = entry
                self._save_cache(cache_path, cache)
                self.stdout.write("CACHED  %5s %-40s -> %s" % (pk, image.title[:40], description))
            if options["apply"]:
                # Cached entries may predate fit_description().
                image.description = fit_description(entry["description"], max_length)
                image.save(update_fields=["description"])
                applied += 1
                self.stdout.write("APPLIED %5s %-40s -> %s" % (pk, image.title[:40], entry["description"]))

        remaining = CustomImage.objects.filter(description="").count()
        self.stdout.write(self.style.SUCCESS(
            "\nGenerated %d description(s), cached at %s. %s %d image(s) still have no description.%s"
            % (
                generated,
                cache_path,
                "Applied %d to the database." % applied if options["apply"]
                else "Run again with --apply to save them.",
                remaining,
                " Stopped at --limit; run again to continue." if stopped_early else "",
            )
        ))

    @contextmanager
    def _single_run_lock(self):
        # A session-level advisory lock is released when the connection closes,
        # so a run killed by a restart never leaves it held.
        if connection.vendor != "postgresql":
            yield True
            return
        acquired = self._try_lock()
        try:
            yield acquired
        finally:
            if acquired:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [ADVISORY_LOCK_ID])

    def _try_lock(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_ID])
            return cursor.fetchone()[0]

    def _generate(self, agent, prompt_text, max_length, image):
        try:
            return agent.execute(
                prompt=prompt_text,
                context={"image": image.pk, "max_length": max_length},
            )
        # BadRequestError: the API rejected this one image (unsupported or
        # unreadable file); any-llm does not always wrap it.
        except (ValidationError, AnyLLMError, BadRequestError) as exc:
            self.stderr.write(self.style.WARNING(
                "FAILED  %5s %-40s -> %s" % (image.pk, image.title[:40], exc)
            ))
            return None

    def _load_cache(self, path):
        if path.exists():
            with path.open() as f:
                return json.load(f)
        return {}

    def _save_cache(self, path, cache):
        with path.open("w") as f:
            json.dump(cache, f, indent=2, sort_keys=True)

"""
Bulk-generate descriptions for CustomImage rows that predate the requirement
that every image have one (see wtrx/images.py -- description is now
blank=False, since it's what alt text is derived from; a blank one falls
back to a filename-derived title).

Reuses the exact same generation path the "Generate description" wand button
already uses in the Images admin -- wagtail_ai's BasicPromptAgent, driven by
the Settings > Agents "Image description" prompt -- rather than
reimplementing prompt/LLM logic.

Results are cached to a JSON file so a dry-run pass never has to re-pay for
the same LLM call twice: inspect or hand-edit the cache, then pass --apply
later to write cached descriptions to the database without regenerating
anything.

    python manage.py backfill_image_descriptions --limit 5           # generate + cache only
    python manage.py backfill_image_descriptions --limit 5 --apply   # generate/reuse cache, then save
    python manage.py backfill_image_descriptions --apply             # apply everything already cached
    python manage.py backfill_image_descriptions --image-id 42 --apply

Idempotent: only ever targets images whose description is still blank, so
partial runs (--limit, Ctrl-C, an API failure) are always safe to re-run.
"""

import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from any_llm.exceptions import AnyLLMError
from wagtail_ai.agents.base import get_agent_settings
from wagtail_ai.agents.basic_prompt import BasicPromptAgent

from wtrx.images import CustomImage

DEFAULT_CACHE_FILE = "image_description_backfill_cache.json"


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
            "--apply",
            action="store_true",
            help="Write cached descriptions to the database. Without this, only the cache file is populated.",
        )

    def handle(self, *args, **options):
        cache_path = Path(options["cache_file"])
        cache = self._load_cache(cache_path)

        images = CustomImage.objects.filter(description="").order_by("pk")
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

        generated = 0
        for image in images:
            key = str(image.pk)
            if key in cache:
                continue
            if options["limit"] is not None and generated >= options["limit"]:
                break
            description = self._generate(agent, prompt_text, max_length, image)
            generated += 1
            if description is None:
                continue
            cache[key] = {"title": image.title, "description": description}
            self._save_cache(cache_path, cache)
            self.stdout.write("CACHED  %5s %-40s -> %s" % (image.pk, image.title[:40], description))

        applied = 0
        if options["apply"]:
            for image in images:
                entry = cache.get(str(image.pk))
                if entry is None:
                    continue
                image.description = entry["description"]
                image.save(update_fields=["description"])
                applied += 1
                self.stdout.write("APPLIED %5s %-40s -> %s" % (image.pk, image.title[:40], entry["description"]))

        self.stdout.write(self.style.SUCCESS(
            "\nGenerated %d description(s), cached at %s. %s"
            % (
                generated,
                cache_path,
                "Applied %d to the database." % applied if options["apply"]
                else "Run again with --apply to save them.",
            )
        ))

    def _generate(self, agent, prompt_text, max_length, image):
        try:
            return agent.execute(
                prompt=prompt_text,
                context={"image": image.pk, "max_length": max_length},
            )
        except (ValidationError, AnyLLMError) as exc:
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

"""
Harvest StreamField block-picker preview values from real site content.

The block picker's previews (see templates/wagtailcore/shared/block_preview.html)
render each block with a placeholder value. Hand-written placeholders go stale
and never look quite like the real thing, so this command walks the live
database, picks the richest real instance of each block type, and writes them
to a JSON file that the blocks read at request time.

Usage:

    python manage.py harvest_block_previews            # write the JSON file
    python manage.py harvest_block_previews --dry-run  # report coverage only

The output file is meant to be reviewed by a human and committed -- it embeds
real editorial copy, so read it before committing and edit anything that
shouldn't be frozen into the admin UI.
"""

import json
import re

from django.core.management.base import BaseCommand

from wagtail.blocks import StreamValue, StructValue
from wagtail.blocks.list_block import ListValue
from wagtail.models import Page, Site

from wtrx.site_settings import IntegrationSettings

from wtrx.blocks import BodyStreamBlock, SectionContentBlock, PREVIEW_DATA_PATH


#: Blocks whose best preview is a specific instance rather than the richest
#: one. Maps a block key to (page title, index among that page's instances) --
#: a negative index counts from the end, so -1 is "the last one on the page".
PINNED_SOURCES = {
    # The panel at the foot of the Take Action page, not the denser one
    # higher up the same page or the regional variant on /canada.
    "feature_panel": ("Take Action", -1),
    # Both conversion blocks should preview as they appear on the homepage.
    "signup_actionkit": ("Home", 0),
    "donate_fundraiseup": ("Home", 0),
}


def _richness(value):
    """
    Score how "full" a block value is, so the best example of each block type
    wins. Counts non-empty leaf values, so an instance that fills in the
    optional image and CTA beats a bare heading-only one.
    """
    if isinstance(value, StreamValue):
        return sum(_richness(child.value) for child in value)
    if isinstance(value, StructValue):
        return sum(_richness(v) for v in value.values())
    if isinstance(value, ListValue):
        return sum(_richness(v) for v in value)
    if value is None:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    # Breadth of filled-in fields should dominate, but among values of the same
    # shape (notably a bare rich-text block, where every instance scores 1) the
    # meatier copy makes the better preview -- hence a small, capped bonus.
    return 1 + min(len(text) // 250, 3)


class Command(BaseCommand):
    help = "Harvest block-picker preview values from real page content."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be harvested without writing the file.",
        )

    def _capture_extras(self, key, block, value):
        """
        Fetch anything a block would otherwise request from a third party at
        render time, so its preview can be served entirely from this file.

        Only ActionKit needs this today: its form markup lives on the client's
        ActionKit instance. Capturing it here means the preview shows the real
        form -- exactly what the page it came from shows -- while the block
        picker itself never talks to ActionKit. This is the one place in the
        harvest that touches the network, and a failure is not fatal: the block
        falls back to its built-in static stand-in.
        """
        if key != "signup_actionkit":
            return None
        short_form_id = value.get("short_form_id", "")
        if not short_form_id:
            return None
        site = Site.objects.filter(is_default_site=True).first() or Site.objects.first()
        if site is None:
            return None
        try:
            config = IntegrationSettings.for_site(site).get_integration_config("actionkit")
        except IntegrationSettings.DoesNotExist:
            config = None
        hostname = config.get("hostname", "") if config else ""
        if not hostname:
            self.stdout.write(
                self.style.WARNING(
                    "ActionKit has no hostname configured; its preview will use "
                    "the built-in stand-in form."
                )
            )
            return None
        form_html = block._fetch_form_html(hostname, short_form_id)
        if not form_html:
            self.stdout.write(
                self.style.WARNING(
                    "Could not fetch the ActionKit form for %r; its preview will "
                    "use the built-in stand-in form." % short_form_id
                )
            )
            return None
        # Strip the form's own scripts. The preview only has to *look* like the
        # real form -- its JS submits to, and fetches from, ActionKit, which is
        # exactly what a preview must not do. Removing them here means no
        # inline script from a third party ever runs in the admin.
        stripped, count = re.subn(
            r"<script\b.*?</script\s*>", "", form_html, flags=re.I | re.S
        )
        self.stdout.write(
            "Captured the live ActionKit form for %r (%d script block(s) stripped)."
            % (short_form_id, count)
        )
        return {"form_html": stripped}

    def handle(self, *args, **options):
        best = {}
        # Every instance seen, in document order, so PINNED_SOURCES can pick a
        # specific one instead of whichever scores highest.
        candidates = {}

        def consider(key, block, value, page):
            score = _richness(value)
            if not score:
                return
            candidates.setdefault(key, []).append((score, block, value, page))
            if score > best.get(key, (0,))[0]:
                best[key] = (score, block, value, page)

        def walk(value, page):
            if isinstance(value, StreamValue):
                for child in value:
                    consider(child.block_type, child.block, child.value, page)
                    walk(child.value, page)
            elif isinstance(value, StructValue):
                for name, child_value in value.items():
                    # ListBlock children carry no block_type of their own, so
                    # name them after the field that holds them (CardGridBlock
                    # .cards -> "card"), which is how they're keyed in the
                    # picker when used as top-level blocks too.
                    block = value.block.child_blocks.get(name)
                    if isinstance(child_value, ListValue) and block is not None:
                        singular = name[:-1] if name.endswith("s") else name
                        for item in child_value:
                            consider(singular, block.child_block, item, page)
                    walk(child_value, page)
            elif isinstance(value, ListValue):
                for item in value:
                    walk(item, page)

        for page in Page.objects.all().specific():
            for field in page._meta.get_fields():
                if field.__class__.__name__ == "StreamField":
                    walk(getattr(page, field.name), page)

        # Only keep keys that name a block the picker can actually offer.
        # The walk also turns up legacy block types still present in old
        # content, and ListBlock field names that match nothing.
        pickable = set(BodyStreamBlock().child_blocks) | set(
            SectionContentBlock().child_blocks
        )
        skipped = sorted(set(best) - pickable)

        # A block that declares its own Meta.preview_value has been given a
        # hand-authored preview on purpose; harvesting it too would leave a
        # dead entry in the file that looks like it is in use but never is.
        hand_authored = {
            name
            for name, block in (
                list(BodyStreamBlock().child_blocks.items())
                + list(SectionContentBlock().child_blocks.items())
            )
            if hasattr(block.meta, "preview_value")
        }

        for key, (title, index) in PINNED_SOURCES.items():
            on_page = [c for c in candidates.get(key, []) if c[3].title == title]
            if not on_page:
                self.stdout.write(
                    self.style.WARNING(
                        "Pinned source for %s not found: no instance on %r. "
                        "Falling back to the richest one." % (key, title)
                    )
                )
                continue
            try:
                best[key] = on_page[index]
            except IndexError:
                self.stdout.write(
                    self.style.WARNING(
                        "Pinned source for %s out of range: %r has %d instance(s)."
                        % (key, title, len(on_page))
                    )
                )

        harvested = {}
        for key, (score, block, value, page) in sorted(best.items()):
            if key not in pickable or key in hand_authored:
                continue
            try:
                harvested[key] = {
                    "_source": "%s (page %d)" % (page.title, page.pk),
                    "_score": score,
                    "value": block.get_prep_value(value),
                }
                extra = self._capture_extras(key, block, value)
                if extra:
                    harvested[key].update(extra)
            except Exception as exc:  # pragma: no cover - defensive
                self.stderr.write("  ! %-24s could not serialise: %s" % (key, exc))

        top_level = set(BodyStreamBlock().child_blocks)
        missing = sorted(top_level - set(harvested) - hand_authored)

        covered = sorted(harvested)
        self.stdout.write(self.style.SUCCESS("Harvested %d block types:" % len(covered)))
        for key in covered:
            self.stdout.write(
                "  %-24s score %-3d  from %s"
                % (key, harvested[key]["_score"], harvested[key]["_source"])
            )
        if missing:
            self.stdout.write(
                self.style.WARNING(
                    "\nNo real content found for %d block type(s):" % len(missing)
                )
            )
            for key in missing:
                self.stdout.write("  %s" % key)
            self.stdout.write(
                "Create a page using these blocks, then re-run this command."
            )
        if hand_authored:
            self.stdout.write(
                "\nHand-authored previews, left alone: %s"
                % ", ".join(sorted(hand_authored))
            )
        if skipped:
            self.stdout.write(
                "Ignored %d key(s) matching no pickable block: %s"
                % (len(skipped), ", ".join(skipped))
            )

        if options["dry_run"]:
            self.stdout.write("\n--dry-run: nothing written.")
            return

        PREVIEW_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        PREVIEW_DATA_PATH.write_text(
            json.dumps(harvested, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        self.stdout.write(
            self.style.SUCCESS("\nWrote %s" % PREVIEW_DATA_PATH)
        )

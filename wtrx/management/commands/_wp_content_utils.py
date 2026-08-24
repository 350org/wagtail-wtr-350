"""
Shared helpers for importing 350.org WordPress content into StreamField
bodies (wtrx.blocks.BodyStreamBlock's "text"/"image" blocks).

Leading underscore keeps this out of manage.py's command autodiscovery
(Django's find_commands() skips filenames starting with "_") — it's a
plain helper module, not itself a command. Used by both
import_350_blog.py and import_350_press_releases.py.
"""

import os
import re
import uuid
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

# WordPress rewrites <img src> to a scaled rendition of the original upload
# (e.g. "photo-700x560.jpg") sized for its theme's display context; the
# unscaled original is almost always still hosted alongside it at the
# un-suffixed filename (e.g. "photo.jpg"). Matches that "-WIDTHxHEIGHT"
# suffix so we can strip it and import the original instead.
_WP_SCALED_IMAGE_RE = re.compile(r"^(?P<base>.+)-\d+x\d+(?P<ext>\.[A-Za-z0-9]+)$")


def _full_size_wp_image_url(url):
    """Strip WordPress's "-WIDTHxHEIGHT" scaled-image suffix from a URL's path, if present."""
    parsed = urlparse(url)
    match = _WP_SCALED_IMAGE_RE.match(parsed.path)
    if not match:
        return url
    return parsed._replace(path=match.group("base") + match.group("ext")).geturl()


def resolve_blogs_target(stderr, style, target_slug):
    """
    Resolve which Blogs page an import command should add children under.

    With --target given, looks it up by slug. Without it, only succeeds if
    exactly one Blogs page exists — sites with more than one (e.g. separate
    "Blog Index" and "Press Releases" pages) must pick explicitly, rather
    than the command silently guessing via Blogs.objects.first().

    Returns the Blogs instance, or None (having already written an error
    to stderr) if it can't be resolved.
    """
    # Deferred import to avoid import-time DB access.
    from wtrx.models import Blogs

    if target_slug:
        blogs = Blogs.objects.filter(slug=target_slug).first()
        if blogs is None:
            stderr.write(style.ERROR(f"No Blogs page found with slug '{target_slug}'."))
        return blogs

    all_blogs = list(Blogs.objects.all())
    if not all_blogs:
        stderr.write(style.ERROR("No Blogs page found. Create one first."))
        return None
    if len(all_blogs) > 1:
        slugs = ", ".join(f"'{b.slug}'" for b in all_blogs)
        stderr.write(
            style.ERROR(f"Multiple Blogs pages exist ({slugs}). Pass --target <slug> to pick one.")
        )
        return None
    return all_blogs[0]

# Block-level tags kept as-is (mapped to themselves or normalized), matching
# wtrx.constants.RICHTEXT_FEATURES_FULL: h2/h3/h4, lists, blockquote.
_BLOCK_TAG_MAP = {
    "h1": "h2",
    "h2": "h2",
    "h3": "h3",
    "h4": "h4",
    "h5": "h4",
    "h6": "h4",
    "p": "p",
    "ul": "ul",
    "ol": "ol",
    "li": "li",
    "blockquote": "blockquote",
}

# Inline tags kept as-is, matching RICHTEXT_FEATURES_FULL: bold, italic, link.
_INLINE_TAG_MAP = {
    "strong": "strong",
    "b": "strong",
    "em": "em",
    "i": "em",
    "a": "a",
    "br": "br",
}

# Tags dropped entirely, along with their contents.
_DROP_ENTIRELY = {"script", "style", "noscript", "iframe", "form", "svg", "button", "input"}

_TAG_FACTORY = BeautifulSoup("", "html.parser")


def _build_clean(node):
    """
    Recursively rebuild a bs4 node's subtree using only tags allowed by
    RICHTEXT_FEATURES_FULL, unwrapping (keeping children/text of) anything
    else and dropping _DROP_ENTIRELY tags along with their contents.

    Returns a list of cleaned bs4 nodes (Tag/NavigableString) suitable for
    appending into a parent tag or serializing directly with str().
    """
    if isinstance(node, Comment):
        return []
    if isinstance(node, NavigableString):
        return [NavigableString(str(node))]
    if not isinstance(node, Tag):
        return []

    name = node.name.lower()
    if name in _DROP_ENTIRELY:
        return []

    mapped = _BLOCK_TAG_MAP.get(name) or _INLINE_TAG_MAP.get(name)
    if not mapped:
        # Unknown/disallowed wrapper (span, div, font, u, sup, ...) — unwrap.
        result = []
        for child in node.children:
            result.extend(_build_clean(child))
        return result

    if mapped == "a":
        href = node.get("href")
        if not href:
            result = []
            for child in node.children:
                result.extend(_build_clean(child))
            return result
        new_tag = _TAG_FACTORY.new_tag("a", href=href)
    else:
        new_tag = _TAG_FACTORY.new_tag(mapped)

    for child in node.children:
        for cleaned_child in _build_clean(child):
            new_tag.append(cleaned_child)
    return [new_tag]


def download_image(session, url, stdout, dry_run=False):
    """
    Download an image from ``url`` and create a CustomImage, or return an
    existing one whose title already matches the source filename (dedup
    across runs, since CustomImage has no dedicated external-URL field).
    """
    if not url:
        return None

    # Deferred import to avoid import-time DB access.
    from wtrx.images import CustomImage

    full_url = _full_size_wp_image_url(url)
    filename = os.path.basename(urlparse(full_url).path) or "imported-image"
    existing = CustomImage.objects.filter(title=filename).first()
    if existing:
        return existing

    if dry_run:
        stdout.write(f"    [dry-run] would download image: {full_url}")
        return None

    from django.core.files.uploadedfile import SimpleUploadedFile

    try:
        resp = session.get(full_url, timeout=30)
        if resp.status_code == 404 and full_url != url:
            # Rare: the unscaled original isn't hosted (e.g. deleted after WP's
            # "big image threshold" processing) — fall back to the scaled copy
            # actually linked in the post content rather than failing the import.
            full_url = url
            filename = os.path.basename(urlparse(url).path) or "imported-image"
            resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        # A single broken/dead image link on the source WP site shouldn't
        # abort the whole import run — skip it and keep going.
        stdout.write(f"    WARNING: failed to download image {full_url} — {exc}")
        return None

    uploaded = SimpleUploadedFile(filename, resp.content)
    image = CustomImage(title=filename, file=uploaded)
    image.save()
    stdout.write(f"    downloaded image: {filename}")
    return image


def _make_image_block(img_tag, caption, session, stdout, dry_run=False):
    if img_tag is None:
        return None
    src = img_tag.get("src")
    if not src:
        return None
    image = download_image(session, src, stdout, dry_run=dry_run)
    if image is None:
        return None
    return {
        "type": "image",
        "value": {
            "image": image.pk,
            "alt_text": img_tag.get("alt", ""),
            "caption": caption,
        },
    }


def _process_nodes(nodes, blocks, pending, session, stdout, dry_run=False):
    """
    Walk a list of top-level bs4 nodes, appending finished blocks to
    ``blocks`` and accumulating consecutive text-eligible HTML fragments in
    ``pending`` (flushed into a single "text" block on any break).
    """

    def flush():
        if not pending:
            return
        combined = "".join(pending).strip()
        pending.clear()
        if combined:
            blocks.append({"type": "text", "value": combined})

    for node in nodes:
        if isinstance(node, Comment):
            continue
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                p = _TAG_FACTORY.new_tag("p")
                p.append(NavigableString(text))
                pending.append(str(p))
            continue
        if not isinstance(node, Tag):
            continue

        name = node.name.lower()
        if name in _DROP_ENTIRELY:
            continue

        # WP's captioned-image wrapper: <div class="wp-caption">...<img>...
        # <p class="wp-caption-text">caption</p></div>, or a <figure>/<figcaption>.
        if name in ("div", "figure") and node.find("img"):
            img_tag = node.find("img")
            caption_tag = node.find(class_="wp-caption-text") or node.find("figcaption")
            caption = caption_tag.get_text(strip=True) if caption_tag else ""
            flush()
            block = _make_image_block(img_tag, caption, session, stdout, dry_run=dry_run)
            if block:
                blocks.append(block)
            continue

        if name == "img":
            flush()
            block = _make_image_block(node, "", session, stdout, dry_run=dry_run)
            if block:
                blocks.append(block)
            continue

        if name in _BLOCK_TAG_MAP:
            imgs = node.find_all("img")
            if imgs and not node.get_text(strip=True):
                # A block whose only content is one or more bare images
                # (e.g. <p><img></p>), no surrounding text.
                flush()
                for img_tag in imgs:
                    block = _make_image_block(img_tag, "", session, stdout, dry_run=dry_run)
                    if block:
                        blocks.append(block)
                continue
            for cleaned in _build_clean(node):
                text = cleaned.get_text(strip=True) if isinstance(cleaned, Tag) else str(cleaned).strip()
                if text:
                    pending.append(str(cleaned))
            continue

        # Unrecognized wrapper tag (div/section with no image, etc.) — flatten
        # by treating its children as if they were top-level nodes.
        _process_nodes(list(node.children), blocks, pending, session, stdout, dry_run=dry_run)

    flush()


def convert_body(content_html, session, stdout, dry_run=False):
    fragment = BeautifulSoup(content_html or "", "html.parser")
    blocks = []
    pending = []
    _process_nodes(list(fragment.children), blocks, pending, session, stdout, dry_run=dry_run)
    for block in blocks:
        block["id"] = str(uuid.uuid4())
    return blocks

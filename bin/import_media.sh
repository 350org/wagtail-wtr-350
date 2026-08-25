#!/usr/bin/env bash
# bin/import_media.sh
#
# Populate local media/ (images, documents) from a local backup of the
# production/staging object storage bucket (an S3 sync, a Divio Object
# Storage download, etc.), so a locally-restored database (see
# bin/import_db.sh) has matching files to serve.
#
# Usage:
#   bash bin/import_media.sh <backup-dir-or-archive> [--force]
#
# Examples:
#   bash bin/import_media.sh ~/Downloads/media-backup/
#   bash bin/import_media.sh ~/Downloads/media-backup.tar.gz
#   bash bin/import_media.sh ~/Downloads/media-backup.tar.gz --force
#
# Invoked via Makefile:
#   make import-media BACKUP=~/Downloads/media-backup/
#   make import-media BACKUP=~/Downloads/media-backup.tar.gz FORCE=1
#
# ---------------------------------------------------------------------------
# What this does
# ---------------------------------------------------------------------------
#
# 1. Accepts either a directory or an archive (.tar, .tar.gz/.tgz, .zip) —
#    extracts archives to a temp dir first.
# 2. Locates the actual media root inside the backup: production.py's S3
#    OPTIONS sets `location: "media"`, so a full bucket sync/backup nests
#    everything under a media/ prefix (media/images/, media/documents/, ...).
#    If the backup has a media/ subdirectory, that's used; otherwise the
#    backup root itself is assumed to already be the media directory
#    (e.g. someone already cd'd into media/ before backing it up).
# 3. Mirrors that directory into the local media/ dir (BASE_DIR/media, per
#    MEDIA_ROOT in wagtail_wtr/settings/base.py) — confirms first unless
#    --force, since this overwrites what's there.
#
# Local dev always serves media from the local filesystem regardless of any
# AWS_*/S3 env vars in .env — wagtail_wtr/settings/dev.py never applies the
# S3 STORAGES override that production.py does — so this is the only way to
# get real images/documents locally instead of broken image links.
#
# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------
#
# rsync (for an efficient, exact mirror) — falls back to cp/rm if not
# installed. tar and/or unzip, only if you pass an archive.

set -euo pipefail

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------

BACKUP=""
FORCE=false
_POSITIONAL=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --force)
            FORCE=true
            shift
            ;;
        -*)
            echo "Error: unknown option '$1'." >&2
            echo "Usage: bash bin/import_media.sh <backup-dir-or-archive> [--force]" >&2
            exit 1
            ;;
        *)
            case "$_POSITIONAL" in
                0) BACKUP="$1" ;;
                *) echo "Error: unexpected positional argument '$1'." >&2
                   echo "Usage: bash bin/import_media.sh <backup-dir-or-archive> [--force]" >&2
                   exit 1 ;;
            esac
            (( _POSITIONAL++ )) || true
            shift
            ;;
    esac
done

if [[ -z "$BACKUP" ]]; then
    echo "Error: <backup-dir-or-archive> argument is required." >&2
    echo "Usage: bash bin/import_media.sh <backup-dir-or-archive> [--force]" >&2
    echo "       make import-media BACKUP=~/Downloads/media-backup/" >&2
    exit 1
fi

if [[ ! -e "$BACKUP" ]]; then
    echo "Error: backup path '$BACKUP' does not exist." >&2
    exit 1
fi

step() {
    echo "→ $*"
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDIA_ROOT="$REPO_ROOT/media"

# ---------------------------------------------------------------------------
# Extract archives to a temp dir; otherwise use the directory as-is
# ---------------------------------------------------------------------------

TMPDIR_CREATED=""
cleanup() {
    if [[ -n "$TMPDIR_CREATED" && -d "$TMPDIR_CREATED" ]]; then
        rm -rf "$TMPDIR_CREATED"
    fi
}
trap cleanup EXIT

SOURCE_ROOT=""

if [[ -d "$BACKUP" ]]; then
    SOURCE_ROOT="$BACKUP"
else
    case "$BACKUP" in
        *.tar.gz | *.tgz)
            command -v tar &>/dev/null || { echo "Error: 'tar' is not installed." >&2; exit 1; }
            TMPDIR_CREATED="$(mktemp -d)"
            step "Extracting $BACKUP"
            tar -xzf "$BACKUP" -C "$TMPDIR_CREATED"
            SOURCE_ROOT="$TMPDIR_CREATED"
            ;;
        *.tar)
            command -v tar &>/dev/null || { echo "Error: 'tar' is not installed." >&2; exit 1; }
            TMPDIR_CREATED="$(mktemp -d)"
            step "Extracting $BACKUP"
            tar -xf "$BACKUP" -C "$TMPDIR_CREATED"
            SOURCE_ROOT="$TMPDIR_CREATED"
            ;;
        *.zip)
            command -v unzip &>/dev/null || { echo "Error: 'unzip' is not installed." >&2; exit 1; }
            TMPDIR_CREATED="$(mktemp -d)"
            step "Extracting $BACKUP"
            unzip -q "$BACKUP" -d "$TMPDIR_CREATED"
            SOURCE_ROOT="$TMPDIR_CREATED"
            ;;
        *)
            echo "Error: '$BACKUP' is not a directory or a recognized archive (.tar, .tar.gz, .tgz, .zip)." >&2
            exit 1
            ;;
    esac
fi

# An archive that itself contains a single top-level directory (the common
# case for a tarball made with `tar -czf backup.tar.gz media/`) should have
# that directory, not the temp extraction root, treated as the source.
_ENTRY_COUNT="$(find "$SOURCE_ROOT" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
if [[ "$_ENTRY_COUNT" -eq 1 ]]; then
    _ONLY_ENTRY="$(find "$SOURCE_ROOT" -mindepth 1 -maxdepth 1)"
    if [[ -d "$_ONLY_ENTRY" ]]; then
        SOURCE_ROOT="$_ONLY_ENTRY"
    fi
fi

# ---------------------------------------------------------------------------
# Locate the media root within the backup
# ---------------------------------------------------------------------------

if [[ -d "$SOURCE_ROOT/media" ]]; then
    SOURCE_ROOT="$SOURCE_ROOT/media"
fi

if [[ -z "$(find "$SOURCE_ROOT" -mindepth 1 -maxdepth 1 2>/dev/null)" ]]; then
    echo "Error: '$SOURCE_ROOT' is empty — nothing to import." >&2
    exit 1
fi

step "Media source: $SOURCE_ROOT"

# ---------------------------------------------------------------------------
# Confirm before overwriting local media/
# ---------------------------------------------------------------------------

if [[ -d "$MEDIA_ROOT" ]] && [[ -n "$(find "$MEDIA_ROOT" -mindepth 1 -maxdepth 1 2>/dev/null)" ]] && [[ "$FORCE" != "true" ]]; then
    echo ""
    echo "Local media/ already has files in it and will be overwritten to"
    echo "exactly match the backup (files not present in the backup are removed)."
    echo ""
    read -r -p "Proceed? [y/N] " CONFIRM
    if [[ "${CONFIRM,,}" != "y" ]]; then
        echo "Aborted."
        exit 0
    fi
    echo ""
fi

mkdir -p "$MEDIA_ROOT"

# ---------------------------------------------------------------------------
# Copy
# ---------------------------------------------------------------------------

step "Importing into $MEDIA_ROOT"

if command -v rsync &>/dev/null; then
    rsync -a --delete "$SOURCE_ROOT/" "$MEDIA_ROOT/"
else
    rm -rf "${MEDIA_ROOT:?}"/*
    cp -r "$SOURCE_ROOT/." "$MEDIA_ROOT/"
fi

FILE_COUNT="$(find "$MEDIA_ROOT" -type f | wc -l | tr -d ' ')"
if [[ "$FILE_COUNT" -eq 0 ]]; then
    echo "Error: import produced no files in '$MEDIA_ROOT' — check the backup contents." >&2
    exit 1
fi

echo ""
echo "Done. Imported $FILE_COUNT files into:"
echo "  $MEDIA_ROOT"
echo ""
echo "make dev will now serve these files locally."

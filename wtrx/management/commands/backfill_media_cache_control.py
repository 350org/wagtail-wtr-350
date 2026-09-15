"""
Backfill the Cache-Control header on existing S3 media objects.

wtrx/management/commands/migrate_media_bucket.py (removed once its job was
done -- see git history) copied media file bytes into this project's Divio
Object Storage bucket via a raw boto3 put_object() call that only ever set
ACL, not CacheControl. Every object that went through that migration -- and
any object uploaded before STORAGES["default"]["OPTIONS"]["object_parameters"]
existed (production.py) -- landed in the bucket with no Cache-Control header
at all. That's exactly what PageSpeed Insights' "Use efficient cache
lifetimes" audit flags for this site's Amazon Web Services / s3.amazonaws.com
entries ("Cache TTL: None"), the large majority of its estimated savings.

New uploads are unaffected: S3Storage.get_object_parameters() already
applies CacheControl on every normal save through Wagtail. This command is a
one-time fix for objects that predate that, or that were copied around it.

Sets the header in place via S3's server-side CopyObject (same bucket, same
key, MetadataDirective=REPLACE) -- no file bytes are re-transferred through
this process. The object's existing ContentType/ContentDisposition/
ContentEncoding/ContentLanguage/Metadata are read back via HeadObject and
carried over unchanged; only CacheControl (and ACL, on an environment that
sets AWS_S3_DEFAULT_ACL -- required on Divio, see AGENTS.md pitfall on S3
storage in production.py) are set. Idempotent: an object whose CacheControl
already matches the desired value is left untouched, so an interrupted run
is safe to re-run.

Uses default_storage's own boto3 client (django-storages' S3Storage) rather
than constructing one by hand, so endpoint_url/region/addressing_style
always match whatever this environment is actually configured for -- this
project's bucket names can contain a literal dot, which breaks hand-rolled
S3 client config that gets addressing_style wrong (see production.py).

Run this ON the environment whose bucket you want to fix (e.g.
`divio app ssh live`, then run it there) so it picks up that environment's
current settings.STORAGES config automatically.

    python manage.py backfill_media_cache_control --dry-run
    python manage.py backfill_media_cache_control
    python manage.py backfill_media_cache_control --prefix media/images/
"""

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Set the configured Cache-Control header on existing S3 media objects that predate it."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prefix",
            default=None,
            help="Only process keys under this prefix (default: the storage's own location, e.g. 'media/').",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would change without writing anything.",
        )

    def handle(self, *args, **options):
        storage_opts = (settings.STORAGES.get("default") or {}).get("OPTIONS") or {}
        if not storage_opts.get("bucket_name"):
            raise CommandError(
                "This environment isn't currently configured for S3 media storage "
                "(settings.STORAGES['default'] has no bucket_name). Nothing to backfill."
            )

        desired_cache_control = default_storage.get_object_parameters("").get("CacheControl")
        if not desired_cache_control:
            raise CommandError(
                "STORAGES['default']['OPTIONS']['object_parameters'] has no CacheControl "
                "configured in this environment -- nothing to backfill against."
            )
        acl = default_storage.default_acl or None

        client = default_storage.connection.meta.client
        bucket = default_storage.bucket_name
        prefix = (options["prefix"] or default_storage.location or "").rstrip("/") + "/"
        dry_run = options["dry_run"]

        self.stdout.write(f"Listing objects under '{prefix}' in '{bucket}'…")
        paginator = client.get_paginator("list_objects_v2")
        checked = updated = skipped = failed = 0

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue  # directory marker, not an actual file
                checked += 1

                try:
                    head = client.head_object(Bucket=bucket, Key=key)
                except Exception as exc:  # noqa: BLE001 -- report and keep going
                    self.stderr.write(self.style.WARNING(f"  FAILED (head): {key} — {exc}"))
                    failed += 1
                    continue

                if head.get("CacheControl") == desired_cache_control:
                    skipped += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f"  [dry-run] would set CacheControl on {key} "
                        f"(currently: {head.get('CacheControl') or 'none'})"
                    )
                    updated += 1
                    continue

                copy_kwargs = {
                    "Bucket": bucket,
                    "Key": key,
                    "CopySource": {"Bucket": bucket, "Key": key},
                    "MetadataDirective": "REPLACE",
                    "Metadata": head.get("Metadata") or {},
                    "ContentType": head.get("ContentType") or "binary/octet-stream",
                    "CacheControl": desired_cache_control,
                }
                for field in ("ContentDisposition", "ContentEncoding", "ContentLanguage"):
                    if head.get(field):
                        copy_kwargs[field] = head[field]
                if acl:
                    copy_kwargs["ACL"] = acl

                try:
                    client.copy_object(**copy_kwargs)
                    updated += 1
                    self.stdout.write(f"  updated: {key}")
                except Exception as exc:  # noqa: BLE001 -- report and keep going
                    self.stderr.write(self.style.WARNING(f"  FAILED (copy): {key} — {exc}"))
                    failed += 1

        self.stdout.write(self.style.SUCCESS(
            "\nChecked %d object(s), %s %d, skipped %d (already correct), %d failed."
            % (
                checked,
                "would update" if dry_run else "updated",
                updated,
                skipped,
                failed,
            )
        ))

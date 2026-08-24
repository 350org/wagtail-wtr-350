"""
migrate_media_bucket management command.

One-time migration for moving media files from an old, separately-configured
S3 bucket into whatever bucket this environment is CURRENTLY configured to
use (settings.STORAGES["default"]) -- e.g. after switching from a manually
provisioned AWS bucket to Divio's managed Object Storage service.

Copies file bytes only, preserving the exact same relative key/path under
the source --prefix in both buckets. CustomImage/CustomRendition rows store
relative paths (not full URLs), so they resolve correctly once the bytes
exist at the same path in whichever bucket is currently active -- no
database changes are made or needed.

Run this ON the environment whose *destination* bucket you want to fill
(e.g. `divio app ssh live`, then run this command there) so it picks up
that environment's current settings.STORAGES config automatically. The old
bucket's credentials are passed as arguments -- they're never read from this
environment's own env vars, since those now point at the new bucket.

Usage:
    python manage.py migrate_media_bucket \\
        --old-bucket my-old-bucket \\
        --old-access-key AKIA... \\
        --old-secret-key ... \\
        [--old-region us-east-1] \\
        [--old-endpoint-url https://...] \\
        [--prefix media/] \\
        [--dry-run]

Safe to re-run: objects already present at the destination key are skipped,
so an interrupted run can simply be repeated.
"""

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# "path" (not virtual-hosted, boto3's default) works for every bucket name,
# including ones containing a dot (e.g. "example.com") — a dotted bucket
# name breaks HTTPS virtual-hosted-style addressing (produces a hostname
# like "example.com.s3.amazonaws.com" that AWS's own wildcard cert doesn't
# cover) — see production.py's matching AWS_S3_ADDRESSING_STYLE default.
_PATH_STYLE_CONFIG = Config(s3={"addressing_style": "path"})


class Command(BaseCommand):
    help = (
        "Copy media files from an old S3 bucket into this environment's "
        "currently-configured bucket (settings.STORAGES['default']), "
        "preserving keys. Run on the destination environment."
    )

    def add_arguments(self, parser):
        parser.add_argument("--old-bucket", required=True, help="Name of the old S3 bucket.")
        parser.add_argument("--old-access-key", required=True)
        parser.add_argument("--old-secret-key", required=True)
        parser.add_argument("--old-region", default="us-east-1")
        parser.add_argument(
            "--old-endpoint-url",
            default=None,
            help="Only needed if the old bucket wasn't on real AWS S3.",
        )
        parser.add_argument(
            "--prefix",
            default="media/",
            help="Key prefix to copy (default: media/, matching this project's "
            "S3Storage 'location' setting).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be copied without writing or reading any file bytes.",
        )

    def handle(self, *args, **options):
        dest_opts = (settings.STORAGES.get("default") or {}).get("OPTIONS")
        if not dest_opts or not dest_opts.get("bucket_name"):
            raise CommandError(
                "This environment isn't currently configured for S3 storage "
                "(settings.STORAGES['default'] has no bucket_name). Nothing to migrate into."
            )
        dest_bucket = dest_opts["bucket_name"]

        old_bucket = options["old_bucket"]
        if old_bucket == dest_bucket:
            raise CommandError("--old-bucket is the same as the currently-configured bucket.")
        prefix = options["prefix"]
        dry_run = options["dry_run"]

        source_client = boto3.client(
            "s3",
            aws_access_key_id=options["old_access_key"],
            aws_secret_access_key=options["old_secret_key"],
            region_name=options["old_region"],
            endpoint_url=options["old_endpoint_url"],
            config=_PATH_STYLE_CONFIG,
        )
        dest_client = boto3.client(
            "s3",
            aws_access_key_id=dest_opts.get("access_key") or None,
            aws_secret_access_key=dest_opts.get("secret_key") or None,
            region_name=dest_opts.get("region_name") or "us-east-1",
            endpoint_url=dest_opts.get("endpoint_url") or None,
            config=_PATH_STYLE_CONFIG,
        )

        self.stdout.write(f"Listing objects under '{prefix}' in '{old_bucket}'…")
        paginator = source_client.get_paginator("list_objects_v2")
        copied, skipped, failed = 0, 0, 0

        for page in paginator.paginate(Bucket=old_bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue  # directory marker, not an actual file

                try:
                    dest_client.head_object(Bucket=dest_bucket, Key=key)
                    self.stdout.write(f"  skip (already exists at destination): {key}")
                    skipped += 1
                    continue
                except ClientError as exc:
                    if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
                        raise

                if dry_run:
                    self.stdout.write(f"  [dry-run] would copy: {key} ({obj['Size']} bytes)")
                    copied += 1
                    continue

                try:
                    body = source_client.get_object(Bucket=old_bucket, Key=key)["Body"].read()
                    dest_client.put_object(Bucket=dest_bucket, Key=key, Body=body)
                    self.stdout.write(f"  copied: {key}")
                    copied += 1
                except Exception as exc:  # noqa: BLE001 -- report and keep going
                    self.stdout.write(self.style.WARNING(f"  FAILED: {key} — {exc}"))
                    failed += 1

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"Dry run complete. Would copy {copied}, skip {skipped}.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Done. Copied {copied}, skipped {skipped}, failed {failed}.")
            )

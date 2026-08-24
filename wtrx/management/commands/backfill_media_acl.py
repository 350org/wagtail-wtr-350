"""
backfill_media_acl management command.

One-time fix-up for objects that were already uploaded to this environment's
CURRENTLY configured media bucket (settings.STORAGES["default"]) before it
was correctly configured to make new uploads public.

New uploads made through the app already get the right ACL automatically
(django-storages sends AWS_S3_DEFAULT_ACL -- see the "default_acl" OPTIONS
key set in production.py -- as part of every PutObject call). This command
is only for objects that predate that fix, or were copied in by
migrate_media_bucket before it started applying the same ACL.

Background: a manually-provisioned AWS bucket (bin/provision.sh) grants
public read via a bucket policy and blocks public ACLs outright. Divio's
"Object Storage" service does the opposite -- its documentation
(docs.divio.com/how-to/interact-storage/) says objects are private by
default and must be given the 'public-read' ACL individually; its
credentials don't grant s3:PutBucketPolicy/PutPublicAccessBlock (confirmed:
that call returns AccessDenied), so a bucket-wide policy can't be
self-applied there. Per-object ACL is the only lever those credentials do
have -- this command calls exactly the same s3:PutObjectAcl operation Divio's
own docs recommend (`aws s3api put-object-acl`), just for every key already
in the bucket instead of one at a time.

Run this ON the environment whose bucket you want to fix (e.g.
`divio app ssh live`, then run this command there) so it picks up that
environment's current settings.STORAGES config and AWS_S3_DEFAULT_ACL
automatically -- same pattern as migrate_media_bucket.

Usage:
    python manage.py backfill_media_acl [--prefix media/] [--dry-run]

Safe to re-run: setting the same ACL on an object that already has it is a
no-op.
"""

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# "path" (not virtual-hosted, boto3's default) works for every bucket name,
# including ones containing a dot — matches production.py's
# AWS_S3_ADDRESSING_STYLE default.
_PATH_STYLE_CONFIG = Config(s3={"addressing_style": "path"})


class Command(BaseCommand):
    help = (
        "Apply this environment's configured AWS_S3_DEFAULT_ACL to every object already "
        "in the currently-configured media bucket (settings.STORAGES['default']). Run on "
        "the target environment."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--prefix",
            default="media/",
            help="Key prefix to fix up (default: media/, matching this project's "
            "S3Storage 'location' setting).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be changed without writing anything.",
        )

    def handle(self, *args, **options):
        dest_opts = (settings.STORAGES.get("default") or {}).get("OPTIONS")
        if not dest_opts or not dest_opts.get("bucket_name"):
            raise CommandError(
                "This environment isn't currently configured for S3 storage "
                "(settings.STORAGES['default'] has no bucket_name). Nothing to fix up."
            )
        bucket_name = dest_opts["bucket_name"]
        acl = dest_opts.get("default_acl")
        if not acl:
            raise CommandError(
                "AWS_S3_DEFAULT_ACL isn't set in this environment -- nothing to backfill. "
                "Set it first (e.g. AWS_S3_DEFAULT_ACL=public-read), matching whatever ACL "
                "new uploads should get, then re-run this command."
            )
        prefix = options["prefix"]
        dry_run = options["dry_run"]

        client = boto3.client(
            "s3",
            aws_access_key_id=dest_opts.get("access_key") or None,
            aws_secret_access_key=dest_opts.get("secret_key") or None,
            region_name=dest_opts.get("region_name") or "us-east-1",
            endpoint_url=dest_opts.get("endpoint_url") or None,
            config=_PATH_STYLE_CONFIG,
        )

        self.stdout.write(f"Listing objects under '{prefix}' in '{bucket_name}'…")
        paginator = client.get_paginator("list_objects_v2")
        fixed, failed = 0, 0

        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue  # directory marker, not an actual file

                if dry_run:
                    self.stdout.write(f"  [dry-run] would set ACL={acl}: {key}")
                    fixed += 1
                    continue

                try:
                    client.put_object_acl(Bucket=bucket_name, Key=key, ACL=acl)
                    self.stdout.write(f"  fixed: {key}")
                    fixed += 1
                except ClientError as exc:  # noqa: BLE001 -- report and keep going
                    self.stdout.write(self.style.WARNING(f"  FAILED: {key} — {exc}"))
                    failed += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"Dry run complete. Would fix {fixed}."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Done. Fixed {fixed}, failed {failed}."))

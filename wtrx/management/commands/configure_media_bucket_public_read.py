"""
configure_media_bucket_public_read management command.

One-time provisioning step for making this environment's CURRENTLY configured
media bucket (settings.STORAGES["default"]) publicly readable -- required
because the app generates unsigned URLs for media (querystring_auth=False in
production.py) and relies on the bucket itself granting public GetObject.

For a manually-provisioned AWS bucket (Render), bin/provision.sh already does
this at setup time. Divio's "Object Storage" service provisions a bucket with
no such policy, so uploaded media returns "403 AccessDenied" on every public
URL until this is applied -- writes succeed (the app's own credentials have
PutObject), but anonymous reads (what a browser makes) don't.

Applies the same shape of policy as bin/provision.sh:
  1. Public access block: allow public bucket policy, still block public ACLs
     (access is granted via bucket policy only, never per-object ACLs).
  2. Bucket policy: public s3:GetObject on every key (media/* in practice,
     since that's the only prefix this app ever writes to).

Run this ON the environment whose bucket you want to fix (e.g.
`divio app ssh live`, then run this command there) so it picks up that
environment's current settings.STORAGES config automatically -- same pattern
as migrate_media_bucket.

Requires the currently-configured credentials to have
s3:PutBucketPolicy / s3:PutPublicAccessBlock permission on the bucket. If the
storage provider's credentials don't grant that (some managed/multi-tenant
object storage services deliberately withhold it), this command fails with a
clear error -- ask the provider to apply an equivalent public-read policy
instead.

Usage:
    python manage.py configure_media_bucket_public_read [--dry-run]

Safe to re-run: both calls are idempotent (put-public-access-block and
put-bucket-policy simply overwrite the existing configuration).
"""

import json

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
        "Apply a public-read bucket policy to this environment's currently-configured "
        "media bucket (settings.STORAGES['default']), matching what bin/provision.sh "
        "sets up for a manually-provisioned AWS bucket. Run on the target environment."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be applied without making any changes.",
        )

    def handle(self, *args, **options):
        dest_opts = (settings.STORAGES.get("default") or {}).get("OPTIONS")
        if not dest_opts or not dest_opts.get("bucket_name"):
            raise CommandError(
                "This environment isn't currently configured for S3 storage "
                "(settings.STORAGES['default'] has no bucket_name). Nothing to configure."
            )
        bucket_name = dest_opts["bucket_name"]
        dry_run = options["dry_run"]

        bucket_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "PublicReadMedia",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket_name}/*",
                }
            ],
        }

        if dry_run:
            self.stdout.write(f"[dry-run] Would configure public access block on '{bucket_name}':")
            self.stdout.write(
                "  BlockPublicAcls=true, IgnorePublicAcls=true, "
                "BlockPublicPolicy=false, RestrictPublicBuckets=false"
            )
            self.stdout.write(f"[dry-run] Would apply bucket policy to '{bucket_name}':")
            self.stdout.write(json.dumps(bucket_policy, indent=2))
            return

        client = boto3.client(
            "s3",
            aws_access_key_id=dest_opts.get("access_key") or None,
            aws_secret_access_key=dest_opts.get("secret_key") or None,
            region_name=dest_opts.get("region_name") or "us-east-1",
            endpoint_url=dest_opts.get("endpoint_url") or None,
            config=_PATH_STYLE_CONFIG,
        )

        self.stdout.write(f"Configuring public access block on '{bucket_name}'...")
        try:
            client.put_public_access_block(
                Bucket=bucket_name,
                PublicAccessBlockConfiguration={
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": False,
                    "RestrictPublicBuckets": False,
                },
            )
        except ClientError as exc:
            raise CommandError(
                f"Failed to set public access block on '{bucket_name}': {exc}\n"
                "This storage provider's credentials may not grant "
                "s3:PutPublicAccessBlock — ask the provider to apply an equivalent "
                "public-read configuration instead."
            ) from exc

        self.stdout.write(f"Applying public-read bucket policy to '{bucket_name}'...")
        try:
            client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(bucket_policy))
        except ClientError as exc:
            raise CommandError(
                f"Failed to apply bucket policy to '{bucket_name}': {exc}\n"
                "This storage provider's credentials may not grant "
                "s3:PutBucketPolicy — ask the provider to apply an equivalent "
                "public-read policy instead."
            ) from exc

        self.stdout.write(self.style.SUCCESS(f"Done. '{bucket_name}' now allows public GetObject."))

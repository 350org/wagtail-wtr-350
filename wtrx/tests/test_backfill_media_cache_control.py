"""
Tests for backfill_media_cache_control (see that command's own docstring for
the full rationale -- migrate_media_bucket, since removed, copied media
objects into the Divio bucket without the CacheControl header every normal
upload gets via STORAGES["default"]["OPTIONS"]["object_parameters"]).

No real S3 calls: default_storage is replaced with a MagicMock exposing just
the attributes/methods the command touches (bucket_name, location,
default_acl, get_object_parameters, connection.meta.client), and the client
itself is mocked so list_objects_v2/head_object/copy_object never leave the
process. moto isn't installed in this project, so this is hand-rolled rather
than using its S3 mock.
"""

from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

S3_STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": "test-bucket",
            "location": "media",
            "object_parameters": {"CacheControl": "max-age=604800, s-maxage=604800, must-revalidate"},
            "default_acl": "public-read",
        },
    },
}

DESIRED_CACHE_CONTROL = "max-age=604800, s-maxage=604800, must-revalidate"


class TestBackfillMediaCacheControlNotConfigured(SimpleTestCase):
    def test_raises_when_no_s3_bucket_configured(self):
        """
        Dev/test settings use FileSystemStorage -- nothing to backfill, and
        the command should say so rather than blow up on a missing attribute.
        """
        with self.assertRaises(CommandError):
            call_command("backfill_media_cache_control")


@override_settings(STORAGES=S3_STORAGES)
class TestBackfillMediaCacheControl(SimpleTestCase):
    def _mock_client(self):
        client = MagicMock()
        paginator = MagicMock()
        client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "media/images/needs-fix.jpg"},
                    {"Key": "media/images/already-ok.jpg"},
                    {"Key": "media/images/dir-marker/"},
                ]
            }
        ]

        def head_object(Bucket, Key):
            if Key == "media/images/needs-fix.jpg":
                return {"CacheControl": None, "ContentType": "image/jpeg", "Metadata": {}}
            return {"CacheControl": DESIRED_CACHE_CONTROL, "ContentType": "image/jpeg", "Metadata": {}}

        client.head_object.side_effect = head_object
        return client

    def _mock_default_storage(self, client):
        storage = MagicMock()
        storage.bucket_name = "test-bucket"
        storage.location = "media"
        storage.default_acl = "public-read"
        storage.get_object_parameters.return_value = {"CacheControl": DESIRED_CACHE_CONTROL}
        storage.connection.meta.client = client
        return storage

    def test_dry_run_reports_without_calling_copy(self):
        client = self._mock_client()
        storage = self._mock_default_storage(client)

        with patch("wtrx.management.commands.backfill_media_cache_control.default_storage", storage):
            out = StringIO()
            call_command("backfill_media_cache_control", "--dry-run", stdout=out)
            output = out.getvalue()

        client.copy_object.assert_not_called()
        self.assertIn("needs-fix.jpg", output)
        self.assertNotIn("already-ok.jpg", output)
        self.assertIn("Checked 2 object(s)", output)
        self.assertIn("would update 1", output)
        self.assertIn("skipped 1", output)

    def test_directory_markers_are_skipped(self):
        client = self._mock_client()
        storage = self._mock_default_storage(client)

        with patch("wtrx.management.commands.backfill_media_cache_control.default_storage", storage):
            call_command("backfill_media_cache_control", "--dry-run", stdout=StringIO())

        checked_keys = [call.kwargs["Key"] for call in client.head_object.call_args_list]
        self.assertNotIn("media/images/dir-marker/", checked_keys)

    def test_apply_replaces_metadata_and_sets_cache_control(self):
        client = self._mock_client()
        storage = self._mock_default_storage(client)

        with patch("wtrx.management.commands.backfill_media_cache_control.default_storage", storage):
            out = StringIO()
            call_command("backfill_media_cache_control", stdout=out)
            output = out.getvalue()

        client.copy_object.assert_called_once()
        kwargs = client.copy_object.call_args.kwargs
        self.assertEqual(kwargs["Bucket"], "test-bucket")
        self.assertEqual(kwargs["Key"], "media/images/needs-fix.jpg")
        self.assertEqual(kwargs["CopySource"], {"Bucket": "test-bucket", "Key": "media/images/needs-fix.jpg"})
        self.assertEqual(kwargs["MetadataDirective"], "REPLACE")
        self.assertEqual(kwargs["CacheControl"], DESIRED_CACHE_CONTROL)
        self.assertEqual(kwargs["ContentType"], "image/jpeg")
        self.assertEqual(kwargs["ACL"], "public-read")
        self.assertIn("updated 1", output)
        self.assertIn("skipped 1", output)

    def test_already_correct_object_is_left_alone(self):
        client = self._mock_client()
        storage = self._mock_default_storage(client)

        with patch("wtrx.management.commands.backfill_media_cache_control.default_storage", storage):
            call_command("backfill_media_cache_control", stdout=StringIO())

        copied_keys = [call.kwargs["Key"] for call in client.copy_object.call_args_list]
        self.assertNotIn("media/images/already-ok.jpg", copied_keys)

    def test_head_object_failure_is_reported_and_does_not_abort_the_run(self):
        client = self._mock_client()
        client.head_object.side_effect = [
            Exception("boom"),
            {"CacheControl": DESIRED_CACHE_CONTROL, "ContentType": "image/jpeg", "Metadata": {}},
        ]
        storage = self._mock_default_storage(client)

        with patch("wtrx.management.commands.backfill_media_cache_control.default_storage", storage):
            err = StringIO()
            call_command("backfill_media_cache_control", stdout=StringIO(), stderr=err)

        self.assertIn("FAILED (head)", err.getvalue())

    def test_no_acl_kwarg_when_default_acl_unset(self):
        """
        A manually-provisioned bucket with a public bucket policy (see
        production.py) leaves AWS_S3_DEFAULT_ACL unset -- sending an ACL
        header there is a hard error, so copy_object must omit it entirely
        rather than pass None.
        """
        client = self._mock_client()
        storage = self._mock_default_storage(client)
        storage.default_acl = None

        with patch("wtrx.management.commands.backfill_media_cache_control.default_storage", storage):
            call_command("backfill_media_cache_control", stdout=StringIO())

        kwargs = client.copy_object.call_args.kwargs
        self.assertNotIn("ACL", kwargs)

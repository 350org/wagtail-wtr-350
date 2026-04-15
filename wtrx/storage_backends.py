from django.contrib.staticfiles.storage import ManifestFilesMixin
from storages.backends.s3 import S3Storage


class S3ManifestStaticStorage(ManifestFilesMixin, S3Storage):
    """S3 storage with manifest-based cache-busting for static files.

    Layers Django's ManifestFilesMixin on top of S3Storage so that
    collectstatic rewrites asset URLs with content-hash suffixes
    (e.g. main.abc123de.css). This allows far-future Cache-Control
    headers without stale assets after deploys, because the filename
    changes whenever the file content changes.
    """

    # Prevent a 500 error if a template references a static file that isn't in
    # the manifest (e.g. on the first deploy after switching storage backends).
    manifest_strict = False

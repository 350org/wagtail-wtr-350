#!/usr/bin/env bash
# Container entrypoint for production (Render, Docker, etc.)
#
# Steps (in order):
#   1. migrate        — apply any pending DB migrations (safe on PostgreSQL;
#                       the migration executor acquires an advisory lock so
#                       concurrent replicas will wait, not double-apply)
#   2. collectstatic  — only when AWS_STORAGE_BUCKET_NAME is NOT set (WhiteNoise
#                       path). The manifest must be written inside this container's
#                       filesystem to be served correctly. When S3 is configured,
#                       collectstatic runs in Render's preDeployCommand (render.yaml)
#                       before the container starts, so it is skipped here.
#   3. gunicorn       — start the application server
#
# Requires: DATABASE_URL, SECRET_KEY, and (for S3) AWS_* env vars.
set -euo pipefail

python manage.py migrate --noinput

if [ -z "${AWS_STORAGE_BUCKET_NAME:-}" ]; then
    # WhiteNoise path: manifest must be written to this container's STATIC_ROOT.
    python manage.py collectstatic --noinput
fi

exec gunicorn wagtail_wtr.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --worker-tmp-dir /dev/shm \
    --access-logfile - \
    --error-logfile -

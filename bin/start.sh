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
# TODO: When S3 is configured (AWS_STORAGE_BUCKET_NAME is set), collectstatic is
# intentionally skipped here and is supposed to run via render.yaml's preDeployCommand.
# However, preDeployCommand has not been confirmed to run reliably — its output does
# not appear in Render's runtime deploy logs. Until this is investigated and resolved,
# after any deploy that changes CSS or other static assets you must manually run:
#   python manage.py collectstatic --noinput
# via the Render dashboard Shell tab (select the running service → Shell).
# See PLAN.md Phase 17 for the tracked fix.

exec gunicorn wagtail_wtr.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --worker-tmp-dir /dev/shm \
    --access-logfile - \
    --error-logfile -

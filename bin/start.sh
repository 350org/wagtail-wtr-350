#!/usr/bin/env bash
# Container entrypoint for production (Render, Docker, etc.)
#
# Steps (in order):
#   1. migrate        — apply any pending DB migrations (safe on PostgreSQL;
#                       the migration executor acquires an advisory lock so
#                       concurrent replicas will wait, not double-apply)
#   2. collectstatic  — always. Static files are served by WhiteNoise from this
#                       container's STATIC_ROOT (see settings/production.py), so the
#                       manifest must be generated inside the container on every
#                       start, in every environment. Static is never on S3; only
#                       media (user uploads) may be. This makes static serving work
#                       on platforms without a pre-deploy hook (e.g. Divio).
#   3. gunicorn       — start the application server
#
# Requires: DATABASE_URL, SECRET_KEY, and (for S3 media) AWS_* env vars.
set -euo pipefail

python manage.py migrate --noinput

python manage.py collectstatic --noinput

exec gunicorn wagtail_wtr.wsgi:application \
    --bind "0.0.0.0:${PORT:-80}" \
    --workers "${WEB_CONCURRENCY:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --worker-tmp-dir /dev/shm \
    --user app \
    --group app \
    --access-logfile - \
    --error-logfile -

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

# HOME=/tmp: gunicorn's --user/--group below only drops the worker processes'
# UID/GID (setuid/setgid) — it does not reset HOME, which stays "/root"
# (inherited from this root-run script). psycopg/libpq always checks for an
# optional client certificate at $HOME/.postgresql/postgresql.crt when
# negotiating SSL; root's home directory is 0700, so the unprivileged app
# worker gets a hard permission error just checking whether that file exists,
# instead of the normal "doesn't exist, skip it" outcome, and every DB
# connection fails. /tmp is world-accessible, so the same "doesn't exist"
# check succeeds there instead. Verified: passing sslcert="" in the DB OPTIONS
# does NOT suppress this lookup (tried and confirmed ineffective) — HOME must
# actually resolve to a directory the app user can read.
exec env HOME=/tmp gunicorn wagtail_wtr.wsgi:application \
    --bind "0.0.0.0:${PORT:-80}" \
    --workers "${WEB_CONCURRENCY:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --worker-tmp-dir /dev/shm \
    --user app \
    --group app \
    --access-logfile - \
    --error-logfile -

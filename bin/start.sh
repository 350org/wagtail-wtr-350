#!/usr/bin/env bash
# Entrypoint for production container (Render, Docker, etc.)
# Runs database migrations then starts gunicorn.
set -euo pipefail

python manage.py migrate --noinput
exec gunicorn wagtail_wtr.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${WEB_CONCURRENCY:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --access-logfile - \
    --error-logfile -

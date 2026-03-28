# Stage 1: Build frontend assets (CSS via Tailwind CLI, JS + fonts copied verbatim)
FROM node:20-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
# Tailwind v4 — no tailwind.config.js; all config is in CSS.
# Copy source files needed for the build: CSS source, JS source, fonts, and
# all templates so Tailwind can scan them for utility class names.
COPY static_src/ ./static_src/
COPY templates/ ./templates/
COPY wtrx/templates/ ./wtrx/templates/
RUN npm run build:prod && \
    cp -r static_src/javascript static_compiled/js && \
    cp -r static_src/fonts static_compiled/fonts

# Stage 2: Python application
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# All python/gunicorn/manage.py invocations use the venv automatically.
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/* && \
    adduser --system --no-create-home --group app

# Install Python dependencies into an isolated venv before copying the full
# source so this layer is cached independently of application code changes.
COPY pyproject.toml ./
RUN python -m venv /app/.venv && \
    /app/.venv/bin/pip install --no-cache-dir .

COPY . .
# Overlay the frontend build output (CSS, JS, fonts) produced in Stage 1.
COPY --from=frontend /app/static_compiled/ ./static_compiled/

# Ensure the entrypoint is executable (git does not reliably preserve +x bits).
RUN chmod +x bin/start.sh

# collectstatic requires valid-looking settings env vars even though no real
# DB or storage backend is used at this stage. Point the dummy DB to /tmp so
# no SQLite file lands in the /app layer.
RUN DJANGO_SETTINGS_MODULE=wagtail_wtr.settings.production \
    SECRET_KEY=collect-static-placeholder \
    DATABASE_URL=sqlite:////tmp/collect-static-placeholder.db \
    ALLOWED_HOSTS=localhost \
    WAGTAILADMIN_BASE_URL=http://localhost \
    python manage.py collectstatic --noinput

RUN chown -R app:app /app
USER app

EXPOSE 8000

CMD ["bin/start.sh"]

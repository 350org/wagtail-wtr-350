# Stage 1: Build frontend assets (CSS via Tailwind CLI, JS + fonts + images copied verbatim)
FROM node:20-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
# Tailwind v4 — no tailwind.config.js; all config is in CSS.
# Copy source files needed for the build: CSS source, JS source, fonts, images,
# and all templates so Tailwind can scan them for utility class names.
COPY static_src/ ./static_src/
COPY templates/ ./templates/
COPY wtrx/templates/ ./wtrx/templates/
RUN npm run build:prod && \
    cp -r static_src/js/. static_compiled/js && \
    cp -r static_src/fonts/. static_compiled/fonts && \
    cp -r static_src/images/. static_compiled/images

# Stage 2: Python application
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# All python/gunicorn/manage.py invocations use the venv automatically.
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/* && \
    adduser --system --no-create-home --group app --home /tmp

# Install Python dependencies into an isolated venv before copying the full
# source so this layer is cached independently of application code changes.
COPY --chown=app:app pyproject.toml ./
RUN python -m venv /app/.venv && \
    /app/.venv/bin/pip install --no-cache-dir .

COPY --chown=app:app . .
# Overlay the frontend build output (CSS, JS, fonts, images) produced in Stage 1.
COPY --chown=app:app --from=frontend /app/static_compiled/ ./static_compiled/

# Ensure the entrypoint is executable (git does not reliably preserve +x bits).
RUN chmod +x bin/start.sh

# STATIC_ROOT is /app/static (see wagtail_wtr/settings/base.py). collectstatic in
# bin/start.sh runs as user app — directory must exist and be writable.
RUN mkdir -p /app/static && chown app:app /app/static

# collectstatic runs at deploy time via render.yaml's preDeployCommand (S3 path)
# or at container startup via bin/start.sh (WhiteNoise path). It is intentionally
# omitted from the Docker build so gunicorn starts immediately when the container
# launches and the health check responds without delay.

# The container starts as root so gunicorn's master can bind privileged port 80
# (Divio's load balancer connects on port 80; it does not inject a PORT env var).
# gunicorn immediately drops worker processes to the unprivileged `app` user
# (see --user/--group in bin/start.sh), so request handling never runs as root.
# On Render, PORT=8000 (render.yaml) overrides the bind port.

EXPOSE 80

CMD ["bin/start.sh"]

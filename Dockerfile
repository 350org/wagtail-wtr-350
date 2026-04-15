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
    cp -r static_src/javascript static_compiled/js && \
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

# collectstatic is intentionally NOT run at build time:
# - When S3 is configured, it runs in render.yaml's preDeployCommand so AWS
#   credentials (available at runtime) are used, not dummy build-time values.
# - When using WhiteNoise, it runs in start.sh so the manifest is written to
#   the correct container filesystem at startup.
USER app

EXPOSE 8000

CMD ["bin/start.sh"]

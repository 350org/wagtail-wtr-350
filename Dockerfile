# Stage 1: Build CSS with Tailwind CLI
FROM node:20-slim AS frontend
WORKDIR /app
COPY package.json .
RUN npm ci
COPY tailwind.config.js ./
COPY static_src/ ./static_src/
COPY templates/ ./templates/
RUN npm run build:prod

# Stage 2: Python application
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e "."

COPY . .
COPY --from=frontend /app/static_compiled/ ./static_compiled/

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "{{ project_name }}.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]

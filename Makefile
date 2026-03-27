.PHONY: help venv dev build build-prod watch migrate createsuperuser setup test load-data build-js build-fonts test-page

help:
	@echo "Available commands:"
	@echo "  make venv             - Create .venv and install all dependencies"
	@echo "  make dev              - Run development server"
	@echo "  make build            - Build CSS and JS (development)"
	@echo "  make build-prod       - Build CSS and JS (production, minified)"
	@echo "  make watch            - Watch and rebuild CSS on change"
	@echo "  make build-js         - Copy JS source to static_compiled"
	@echo "  make build-fonts      - Copy font files to static_compiled"
	@echo "  make migrate          - Run database migrations"
	@echo "  make createsuperuser  - Create admin user"
	@echo "  make setup            - Interactive site setup"
	@echo "  make test             - Run test suite"
	@echo "  make load-data        - Migrate + load demo fixtures"
	@echo "  make test-page        - Create (or refresh) the block test page"

venv:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e ".[dev]"
	@echo ""
	@echo "Virtual environment ready. Activate with: source .venv/bin/activate"

dev:
	python manage.py runserver

build-js:
	rm -rf static_compiled/js/*
	cp -r static_src/javascript/* static_compiled/js/

build-fonts:
	mkdir -p static_compiled/fonts/fonts
	cp static_src/fonts/fonts/*.woff* static_compiled/fonts/fonts/

build: build-js build-fonts
	npm run build

build-prod: build-js build-fonts
	npm run build:prod

watch:
	npm run start

migrate:
	python manage.py migrate

createsuperuser:
	python manage.py createsuperuser

setup:
	python manage.py setup_site

test:
	python manage.py test wagtail_wtr

load-data:
	python manage.py migrate
	@test -f fixtures/demo.json && python manage.py loaddata fixtures/demo.json || echo "No demo fixtures yet — skipping loaddata"
	python manage.py collectstatic --noinput

test-page:
	python manage.py create_test_page --force

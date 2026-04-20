.PHONY: help venv dev build build-prod watch migrate createsuperuser setup test load-data build-js build-fonts build-images test-page provision

help:
	@echo "Available commands:"
	@echo "  make venv                        - Create .venv and install all dependencies"
	@echo "  make dev                         - Run development server"
	@echo "  make build                       - Build CSS and JS (development)"
	@echo "  make build-prod                  - Build CSS and JS (production, minified)"
	@echo "  make watch                       - Watch and rebuild CSS on change"
	@echo "  make build-js                    - Copy JS source to static_compiled"
	@echo "  make build-fonts                 - Copy font files to static_compiled"
	@echo "  make build-images                - Copy static images to static_compiled"
	@echo "  make migrate                     - Run database migrations"
	@echo "  make createsuperuser             - Create admin user"
	@echo "  make setup                       - Interactive site setup"
	@echo "  make test                        - Run test suite"
	@echo "  make load-data                   - Migrate + load demo fixtures"
	@echo "  make test-page                   - Create (or refresh) the block test page"
	@echo "  make provision SITE=x ENV=y      - Provision AWS S3 bucket + IAM user (ENV: staging|production)"
	@echo "                 [PROFILE=p]         Optional: AWS CLI profile (default: default)"

venv:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e ".[dev]"
	@echo ""
	@echo "Virtual environment ready. Activate with: source .venv/bin/activate"

dev:
	python manage.py runserver

build-js:
	mkdir -p static_compiled/js
	rm -rf static_compiled/js/*
	cp -r static_src/javascript/* static_compiled/js/

build-fonts:
	mkdir -p static_compiled/fonts
	rm -rf static_compiled/fonts/*
	cp -r static_src/fonts/* static_compiled/fonts/

build-images:
	mkdir -p static_compiled/images
	rm -rf static_compiled/images/*
	cp -r static_src/images/* static_compiled/images/

build: build-js build-fonts build-images
	npm run build

build-prod: build-js build-fonts build-images
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
	python manage.py test wtrx wagtail_wtr

load-data:
	python manage.py migrate
	@test -f fixtures/demo.json && python manage.py loaddata fixtures/demo.json || echo "No demo fixtures yet — skipping loaddata"
	python manage.py collectstatic --noinput

test-page:
	python manage.py create_test_page --force

provision:
	@if [ -z "$(SITE)" ]; then echo "Error: SITE is required. Usage: make provision SITE=mysite ENV=production"; exit 1; fi
	@bash bin/provision.sh "$(SITE)" "$(ENV)" $(if $(PROFILE),--profile "$(PROFILE)")

ENV ?= production

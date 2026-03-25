.PHONY: help dev build build-prod watch migrate createsuperuser setup test load-data

help:
	@echo "Available commands:"
	@echo "  make dev              - Run development server"
	@echo "  make build            - Build CSS (development)"
	@echo "  make build-prod       - Build CSS (production, minified)"
	@echo "  make watch            - Watch and rebuild CSS on change"
	@echo "  make migrate          - Run database migrations"
	@echo "  make createsuperuser  - Create admin user"
	@echo "  make setup            - Interactive site setup"
	@echo "  make test             - Run test suite"
	@echo "  make load-data        - Migrate + load demo fixtures"

dev:
	python manage.py runserver

build:
	npm run build

build-prod:
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
	python manage.py test

load-data:
	python manage.py migrate
	@test -f fixtures/demo.json && python manage.py loaddata fixtures/demo.json || echo "No demo fixtures yet — skipping loaddata"
	python manage.py collectstatic --noinput

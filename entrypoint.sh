#!/bin/sh
set -e

uv run python manage.py migrate --noinput

uv run python manage.py createsuperuser --noinput || \
    echo "Superuser already exists, skipping creation."

exec uv run gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}
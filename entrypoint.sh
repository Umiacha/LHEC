#!/bin/sh
set -e

# Проверяем итоговые настройки Django до миграций и запуска сервера.
uv run python - <<'PY'
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
from django.conf import settings

if settings.DEBUG:
    raise SystemExit("Отказ в запуске: DEBUG=True в окружении Docker.")
PY

uv run python manage.py migrate --noinput

uv run python manage.py createsuperuser --noinput || \
    echo "Superuser already exists, skipping creation."

exec uv run gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}

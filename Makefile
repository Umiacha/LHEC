.PHONY: check-migrations show-migrations makemigrations migrate run tailwind dev

MANAGE = uv run python manage.py


# Проверить, не требуются ли новые миграции.
# Команда завершится с ошибкой, если модели изменены,
# но соответствующие миграции не созданы.
check-migrations:
	$(MANAGE) makemigrations --check --dry-run


# Показать существующие миграции и их состояние.
show-migrations:
	$(MANAGE) showmigrations


# Создать новые миграции.
makemigrations:
	$(MANAGE) makemigrations


# Применить миграции.
migrate:
	$(MANAGE) migrate


# Запустить Django development server.
run:
	$(MANAGE) runserver


# Запустить Tailwind в watch-режиме.
tailwind:
	npm run css:watch


# Запустить Django и Tailwind одновременно.
dev:
	$(MAKE) --no-print-directory -j2 run tailwind
.PHONY: check-mysql check-migrations show-migrations makemigrations migrate run gunicorn-run tailwind dev styles

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


# Диагностика MySQL: предупреждения не блокируют, ошибки останавливают make.
check-mysql:
	$(MANAGE) check_mysql


# Применить миграции.
migrate: check-mysql
	$(MANAGE) migrate


# Запустить Django development server.
run: check-mysql
	$(MANAGE) runserver


# Запуск без DEBUG=режима
gunicorn-run: check-mysql
	DJANGO_DEBUG=False \
	DJANGO_SERVE_STATIC=True \
	DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 \
	uv run gunicorn config.wsgi:application \
	  --bind 127.0.0.1:8000 \
	  --workers 1 \
	  --access-logfile - \
	  --error-logfile -


# Собрать CSS и обновить файлы, раздаваемые WhiteNoise / веб-сервером.
styles: css
	$(MANAGE) collectstatic --noinput


# Запустить Tailwind в watch-режиме.
tailwind:
	npm run css:watch


# Запустить Django и Tailwind одновременно.
dev:
	$(MAKE) --no-print-directory -j2 run tailwind



# Проверить: есть ли суперпользователь
check-admin-exist:
	$(MANAGE) shell -c "from django.contrib.auth import get_user_model; print(get_user_model().objects.filter(is_superuser=True).exists())"


# Создать тестового админа
create-test-admin:
	$(MANAGE) createsuperuser --noinput

# GNU gettext must be installed (e.g. apt install gettext).
.PHONY: messages compilemessages
messages:
	$(MANAGE) makemessages -l en --ignore=.venv --ignore=node_modules

compilemessages:
	$(MANAGE) compilemessages --ignore=.venv --ignore=node_modules

# Только изолированный локальный кластер; DATABASE_URL здесь не используется.
.PHONY: db-start db-stop db-status db-reset
db-start:
	uv run python scripts/dev_db.py start

db-stop:
	uv run python scripts/dev_db.py stop

db-status:
	uv run python scripts/dev_db.py status

db-reset:
	uv run python scripts/dev_db.py reset

.PHONY: css release release-prepare release-css release-translations release-requirements
css:
	npm run css:build

# Единый сценарий: чистый HEAD -> подготовка в снимке -> упаковка Python.
# Одна shell-сессия сохраняет временный каталог и гарантирует очистку при ошибке.
release:
	@set -eu; \
	if [ -n "$$(git status --porcelain --untracked-files=all)" ]; then \
		echo "Рабочее дерево не чистое: сохраните изменения в коммите перед make release." >&2; exit 1; \
	fi; \
	for tool in python3 uv npm msgfmt; do command -v "$$tool" >/dev/null || { echo "Для сборки требуется $$tool." >&2; exit 1; }; done; \
	release_root="$$(pwd)"; \
	release_commit="$$(git rev-parse HEAD)"; \
	release_timestamp="$$(git show -s --format=%ct HEAD)"; \
	release_work="$$(mktemp -d)"; \
	trap 'rm -rf "$$release_work"' EXIT; \
	trap 'exit 1' HUP INT TERM; \
	mkdir "$$release_work/source"; \
	git archive --format=tar HEAD > "$$release_work/source.tar"; \
	tar -xf "$$release_work/source.tar" -C "$$release_work/source"; \
	env -u DJANGO_SETTINGS_MODULE -u UV_PROJECT_ENVIRONMENT -u VIRTUAL_ENV \
		$(MAKE) --no-print-directory -C "$$release_work/source" release-prepare; \
	python3 "$$release_work/source/scripts/build_release.py" \
		--source "$$release_work/source" --output "$$release_root/dist" \
		--commit "$$release_commit" --timestamp "$$release_timestamp"

# Внутренние шаги выполняются последовательно даже при make -j release.
release-prepare:
	uv sync --locked --no-dev
	$(MAKE) release-requirements
	$(MAKE) release-css
	$(MAKE) release-translations

release-requirements:
	uv export --locked --no-dev --no-emit-project --output-file requirements.txt > /dev/null

release-css:
	npm ci
	$(MAKE) css

# Не загружаем settings/.env; пересобираем и отслеживаемые Git каталоги .mo.
release-translations:
	find locale -name '*.mo' -type f -delete
	uv run --no-sync django-admin compilemessages --ignore=.venv --ignore=node_modules

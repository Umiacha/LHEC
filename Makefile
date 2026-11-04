.PHONY: check-migrations show-migrations makemigrations migrate run tailwind dev styles

MANAGE = uv run python manage.py

.PHONY: release-requirements
# Вызывать при подготовке каждого релиза локально или в CI.
# Устаревший uv.lock приводит к ошибке, а не обновляется при экспорте.
release-requirements:
	uv export --locked --no-dev --no-emit-project --output-file requirements.txt > /dev/null


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
run: db-start
	$(MANAGE) runserver


# Собрать CSS и обновить файлы, раздаваемые WhiteNoise / веб-сервером.
styles:
	npm run css:build
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

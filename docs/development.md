# Разработка и локальный запуск

Python 3.12, Django 5.2, MySQL, mysqlclient; Tailwind CSS 4, Node.js и npm;
uv, GNU make и GNU gettext. Установка готовой поставки описана в
[руководстве администратора](deploy.md).

## Локальная разработка и база данных

Команды выполняются из корня проекта. На Ubuntu:

```sh
sudo apt install mysql-server default-libmysqlclient-dev build-essential pkg-config python3.12-dev gettext
uv sync --locked
npm ci
cp .env.example .env
make db-start
```

Задайте в `.env` секретный `DJANGO_SECRET_KEY` и пароль БД; для разработки
используйте `DJANGO_DEBUG=True`. Переменные процесса имеют приоритет над `.env`.

Один раз подготовьте пользователя через `sudo mysql`:

```sql
CREATE USER 'lhec_dev'@'localhost' IDENTIFIED BY 'replace-with-local-password';
GRANT ALL PRIVILEGES ON `lhecdev`.* TO 'lhec_dev'@'localhost';
GRANT ALL PRIVILEGES ON `test\_lhecdev`.* TO 'lhec_dev'@'localhost';
```

Подключение в `.env` (спецсимволы реквизитов кодируются для URL):

```dotenv
DATABASE_URL=mysql://lhec_dev:replace-with-local-password@%2Frun%2Fmysqld%2Fmysqld.sock/lhecdev
# TCP:
# DATABASE_URL=mysql://lhec_dev:password@127.0.0.1:3306/lhecdev
```

```sh
make db-prepare
make migrate
make styles
uv run python manage.py createsuperuser
make run
```

Сайт: http://127.0.0.1:8000/, админка: http://127.0.0.1:8000/admin/.
`make dev` запускает Django и отслеживание CSS; `make gunicorn-run` —
локальный Gunicorn с `DEBUG=False` и WhiteNoise.

| Команда | Действие |
| --- | --- |
| `make db-prepare` | Создать выделенную `lhecdev`, если отсутствует |
| `make db-check` | Проверить подключение |
| `make db-status` | Проверить службу и подключение |
| `make db-start` / `make db-stop` | Запустить / остановить общую службу MySQL через systemd |
| `make db-reset` | После подтверждения `lhecdev` пересоздать dev-БД и применить миграции |

Dev-скрипт допускает только локальные `lhecdev` / `lhec_dev` и порт 3306;
не создаёт пользователей и не выдаёт права. Сброс не удаляет файлы загрузок.
`db-stop` требует подтверждения `mysql` и затрагивает всю системную службу.

## Повседневная разработка

### CSS и шаблоны

`make styles` собирает CSS и выполняет `collectstatic`, `make css` собирает
только CSS, `make tailwind` отслеживает изменения.
Компоненты описаны в [дизайн-системе](design-system.md).

### Миграции

```sh
make makemigrations
make check-migrations
make migrate
make show-migrations
```

Начальная история рассчитана на пустую MySQL-БД. Подключение старой схемы
через `--fake` / `--fake-initial` не поддерживается. После первого деплоя
изменения оформляются новыми миграциями.

Backend `config.db.mysql` создаёт таблицы InnoDB / utf8mb4 /
`utf8mb4_0900_ai_ci` / DYNAMIC, включая служебные и M2M-таблицы.
Параметры соединения и требования к серверу — в
[разделе MySQL](deploy.md#подключение-mysql).

### Сравнение строк и ограничения

- Логины, slug, ФИО и названия используют `utf8mb4_0900_as_ci`:
  регистр не учитывается, е/ё и диакритика различаются.
- URL используют `utf8mb4_0900_bin`, включая регистр пути и параметров.
  URL научного профиля ограничен 500 символами.
- `NormalizedNameField` нормализует NFC и внешние пробелы;
  `CanonicalSlugField` также приводит slug к нижнему регистру.
  Прямой SQL и SQL-выражения могут обходить нормализацию Python.
- Уникальность участия и единственного руководителя проекта обеспечивается
  индексами, в том числе по вычисляемым полям. CHECK ограничивают годы
  и допустимое сочетание сведений об участнике.

### Даты и часовые пояса

`USE_TZ=True`, `TIME_ZONE=Europe/Moscow`; в БД хранятся UTC-значения.
Используйте `timezone.now()` и `timezone.localdate()`. Границы локального дня
вычисляйте в Python и передавайте диапазоном aware datetime.
Текущие запросы не требуют timezone-таблиц MySQL. Добавление `__date`, `Trunc`,
`datetimes()` или `date_hierarchy` требует проверки SQL-преобразований зон.

### Проверки и тесты

Тестовый пользователь должен иметь права на отдельную `test_lhecdev`.
Для полного сценария из исходников:

```sh
make check-ubuntu
```

Сценарий собирает CSS и статику, проверяет MySQL, Django и миграции,
выполняет тесты на БД с нуля, включая HTTP-проверки runserver и Gunicorn.
Используются временные хранилища; успешный запуск завершается сообщением
`Ubuntu: checks, fresh migrations, tests and both HTTP servers passed.`
Существующая тестовая БД блокирует автоматический запуск.

Для отдельных проверок:

```sh
uv run python manage.py check
uv run python manage.py collectstatic --noinput
DJANGO_SECURE_SSL_REDIRECT=False uv run python manage.py test
make check-migrations
uv run python -m unittest tests.test_release tests.test_dev_db -v
```

Релизный архив проверяйте отдельно: распакуйте его в новый каталог, установите
зависимости через pip и выполните процедуру из [deploy.md](deploy.md#установка-релиза)
на отдельной пустой БД и временных хранилищах. Для локального HTTP отключите
Secure-cookie, доверие к прокси и HTTPS-редирект; при `check --deploy` учитывайте
эти отличия окружения. Проверьте вход, статику и доступ к файлам.
Проверка на Ubuntu не подтверждает сборку mysqlclient и работу служб в FreeBSD Jail.

## Переводы интерфейса

```sh
make messages
# Заполните msgstr в locale/en/LC_MESSAGES/django.po.
make compilemessages
```

GNU gettext должен быть в `PATH`; `.po` и `.mo` сохраняются в Git вместе.

## Зависимости и lock-файлы

Зависимости редактируются в `pyproject.toml`:

```sh
uv lock
uv sync --locked
make release-requirements
```

Сохраняйте `pyproject.toml`, `uv.lock` и `requirements.txt` вместе.
`requirements.txt` экспортируется из lock-файла с хешами и служит источником
установки зависимостей готового релиза. Для сборки mysqlclient нужны системные
клиентские библиотеки, заголовки и компилятор.

## Подготовка релиза у разработчика или в CI

Нужны Git, GNU make, Python 3.12, uv, Node.js, npm и GNU gettext;
БД и `.env` для сборки не требуются.

1. Задайте `project.version` в `pyproject.toml` и обновите lock-файл.
   Для `0.x` исправления повышают patch, новые возможности и изменения
   совместимости — minor. Опубликованные номера не переиспользуются.
2. Выполните проверки проекта и `make release-requirements`.
3. Сохраните изменения в коммите; рабочее дерево должно быть чистым.
4. Выполните `make release`. Для выпуска создайте тег `vX.Y.Z` на этом коммите.

Сборка использует снимок `HEAD`, устанавливает зависимости, экспортирует
`requirements.txt`, собирает CSS и переводы. Результат в `dist/`:
`lhec-<версия>-<полный-hash>.tar.gz` и `.tar.gz.sha256`.
`RELEASE.json` содержит версию, коммит, время коммита и список файлов.

Поставка включает код, миграции, шаблоны, готовые CSS и переводы,
`requirements.txt`, `Makefile.prod` и `.env.example`. Тесты, dev-инструменты,
секреты и пользовательские данные не включаются. Состав задаётся в
`scripts/build_release.py`; при добавлении приложений и ресурсов обновите его.
`collectstatic` выполняется при установке на сервере.

## API парсера библиографических файлов

Требования:

- Python-зависимости проекта.
- Для `find_duplicates` — настроенное окружение Django и доступ к БД.
- Входной файл BibTeX или RIS в UTF-8, до 2 МБ, с одной публикацией.

`publications/importers.py` разбирает ровно одну публикацию из BibTeX или RIS.

Сам парсер не сохраняет записи,
не загружает вложения и не обращается к внешним API.

Пример для Python-кода приложения; `uploaded_file` — Django `UploadedFile`.
Для текста или байтов формат передаётся явно: `format='bibtex'` или `format='ris'`.

```python
from publications.importers import parse_publication, find_duplicates

result = parse_publication(uploaded_file)
initial = result.data
errors = result.errors
warnings = result.warnings
unmapped = result.unmapped_fields
matches = find_duplicates(result)
```

`data` содержит значения полей `Publication` для формы, `errors` — ошибки полей,
`warnings` — предупреждения о неизвестном типе и неперенесённых полях,
`unmapped_fields` — эти поля с исходными значениями. Поиск дублей возвращает
`DuplicateMatch(publication, reason)`.

Пустой, повреждённый файл или несколько записей вызывают
`PublicationImportError`. Недостающие обязательные значения остаются в
`result.errors`: форму можно заполнить вручную. Неизвестный тип заменяется
на «Другое» с предупреждением. Публикация всегда предлагается как черновик.

Поиск дублей сравнивает нормализованный DOI, а при отсутствии DOI во входных
данных — название без различий регистра, пробелов и пунктуации вместе с годом.
Он включает неопубликованные карточки. Для редактирования можно передать
`exclude_pk`, для ограничения области поиска — `queryset`. Это кандидаты для
проверки человеком; записи не изменяются.

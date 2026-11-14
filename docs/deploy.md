# Развёртывание в FreeBSD Jail

Установка готового релиза в существующую инфраструктуру MySQL, reverse proxy
и управления службами. Команды выполняются из окончательного каталога релиза
с окружением службы; пути указаны внутри Jail.

## Требования и состав поставки

Python 3.12, MySQL >= 8.0.16, InnoDB, utf8mb4. MariaDB не поддерживается
текущей диагностикой. Сквозная установка в FreeBSD Jail требует проверки
на целевой площадке.

Поставка: `lhec-<версия>-<hash>.tar.gz` и `.sha256`. В архиве — код,
миграции, шаблоны, готовые CSS и переводы, `requirements.txt`, `Makefile.prod`
и `RELEASE.json`. Git, uv и Node.js на сервере не требуются.
[Подготовка поставки](development.md#подготовка-релиза-у-разработчика-или-в-ci).

Для сборки mysqlclient внутри Jail приложения нужны клиентские библиотеки
MySQL, заголовки, C-компилятор и pkg-config; для Pillow — JPEG и zlib.
Если эти зависимости уже доступны, повторная установка не требуется. Пример установки недостающих зависимостей FreeBSD с клиентом MySQL 8.0:

```sh
pkg install python312 py312-pip mysql80-client jpeg-turbo pkgconf
```

## Размещение приложения и постоянных данных

Каждый релиз устанавливается в отдельный окончательный каталог со своей
`.venv`, созданной на целевой системе.

| Настройка | Содержимое и доступ |
| --- | --- |
| `STATIC_ROOT` | Статика текущего релиза; запись при `collectstatic`, чтение прокси |
| `MEDIA_ROOT` | Постоянные публичные загрузки; запись приложению, чтение прокси |
| `PRIVATE_PUBLICATIONS_ROOT` | Постоянные вложения и учебные материалы; доступ только приложению |

Закрытое хранилище не публикуется через прокси. Все учебные материалы,
включая общедоступные, выдаёт Django с проверкой доступа.

## Конфигурация приложения

Настройки передаются через окружение либо `.env` в корне релиза;
окружение имеет приоритет. Изменения требуют перезапуска процессов.
Серверные пути задаются абсолютными.

Пример: TLS, HTTP-редирект и HSTS обеспечивает прокси, статику раздаёт он же.

```dotenv
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<secret>
DJANGO_ALLOWED_HOSTS=lhec.example.org
DATABASE_URL=mysql://lhec:<password>@db.example.org:3306/lhec
DJANGO_SERVE_STATIC=False
STATIC_ROOT=/var/www/lhec/releases/<hash>/staticfiles
MEDIA_ROOT=/var/db/lhec/media
PRIVATE_PUBLICATIONS_ROOT=/var/db/lhec/private
DJANGO_SESSION_COOKIE_SECURE=True
DJANGO_CSRF_COOKIE_SECURE=True
DJANGO_TRUST_PROXY_SSL_HEADER=True
DJANGO_SECURE_SSL_REDIRECT=False
DJANGO_SECURE_HSTS_SECONDS=0
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=False
DJANGO_SECURE_HSTS_PRELOAD=False
DJANGO_SILENCED_SECURITY_CHECKS=security.W004,security.W008
```

Секрет создаётся один раз и сохраняется при обновлениях:

```sh
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(64))'
```

Все процессы используют один ключ. Его замена сбрасывает подписанные данные,
включая сессии; резервные ключи через окружение не поддерживаются.

Прокси передаёт исходный `Host` и перезаписывает `X-Forwarded-Proto`;
upstream доступен только доверенному прокси. Если HTTPS-политики обеспечивает
Django, задайте `DJANGO_SECURE_SSL_REDIRECT=True` и необходимые HSTS-параметры,
убрав соответствующие исключения проверок. Допустимы только исключения
W004/W005/W008/W021, соответствующие принятой политике.
См. [проверки безопасности Django](https://docs.djangoproject.com/en/5.2/ref/checks/#security)
и [настройку доверия к прокси](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header).

## Подключение MySQL

Администратор предоставляет пустую выделенную БД и доступ из Jail:
TCP либо Unix-сокет, совместимую аутентификацию и необходимые параметры TLS.
Спецсимволы реквизитов кодируются для URL. Пример сокета:

```dotenv
DATABASE_URL=mysql://lhec:password@%2Fvar%2Frun%2Fmysql%2Fmysql.sock/lhec
```

Путь должен быть доступен внутри Jail. TLS-параметры клиента передаются
параметрами `DATABASE_URL`, например `?ssl_ca=/path/to/ca.pem`;
сертификаты и проверка сервера согласуются с политикой площадки.
См. [параметры подключения Django](https://docs.djangoproject.com/en/5.2/ref/databases/#connecting-to-the-database).

| Область | Принятая конфигурация |
| --- | --- |
| Сервер | MySQL >= 8.0.16 с CHECK и вычисляемыми индексируемыми полями |
| Таблицы | InnoDB, utf8mb4, DYNAMIC; задаются backend приложения при создании |
| Collation | `utf8mb4_0900_ai_ci`, `utf8mb4_0900_as_ci`, `utf8mb4_0900_bin` |
| Индексы | Бюджет не менее 3028 байт; страница InnoDB не менее 16384 байт |
| Соединения | utf8mb4, READ COMMITTED, `CONN_MAX_AGE=0`, health checks |
| SQL-режимы | Добавляются `STRICT_TRANS_TABLES` и `NO_ENGINE_SUBSTITUTION`; остальные сохраняются |
| Время | UTC в БД, отображение Europe/Moscow средствами Python; timezone-таблицы текущим запросам не нужны |

Глобальные настройки сервера менять не требуется. Сервер должен разрешать
необходимые сессионные настройки и DDL. Лимит соединений согласуется с числом
процессов/потоков Gunicorn и параллельными служебными командами.

Службе нужны SELECT/INSERT/UPDATE/DELETE в БД приложения; миграциям дополнительно
CREATE/ALTER/DROP/INDEX/REFERENCES. Глобальные права и создание тестовых БД
production-службе не нужны. Миграции создают все таблицы и ограничения.

## Установка релиза

Первый деплой выполняется на пустую БД. Присоединение существующей схемы
через `--fake` / `--fake-initial` не поддерживается.

1. Сверьте SHA-256 и распакуйте архив в окончательный каталог релиза.
2. Создайте окружение и установите зависимости:

   ```sh
   export PATH="/usr/local/bin:$PATH"
   python3.12 -m venv .venv
   .venv/bin/python -m pip install --require-hashes -r requirements.txt
   .venv/bin/python -m pip check
   ```

3. Подготовьте окружение службы и доступ к хранилищам.
4. Выполните:

   ```sh
   make -f Makefile.prod check
   make -f Makefile.prod check-migrations
   make -f Makefile.prod migrate
   make -f Makefile.prod collectstatic
   make -f Makefile.prod create-superuser.
   ```
Наличие сервера MySQL, в том числе вне Jail приложения, не гарантирует
наличия клиентских библиотек в Jail

5. Подключите службу и прокси, запустите приложение и проверьте развёртывание.

Миграции создают группу «Сотрудники» с правом просмотра внутренних материалов
и исходные темы работ. Суперпользователь создаётся отдельно.

## Запуск службы и подключение reverse proxy

Служба задаёт пользователя, каталог релиза, окружение и параметры Gunicorn:

```sh
export GUNICORN_CMD_ARGS='--bind unix:/var/run/lhec/gunicorn.sock --workers 2 --access-logfile - --error-logfile -'
make -f Makefile.prod gunicorn-run
```

При прямом запуске Gunicorn выполните `.venv/bin/python manage.py check_mysql`
обязательным предварительным шагом с тем же окружением и остановкой при ошибке.
WSGI entry point: `config.wsgi:application`.

Прокси направляет запросы к upstream, `/static/` — в `STATIC_ROOT`,
`/media/` — в `MEDIA_ROOT`. При `DJANGO_SERVE_STATIC=False` WhiteNoise
не обслуживает запросы, но используется при сборке статики.
Троттлинг форм входа, лимиты загрузок, таймауты и TLS задаются инфраструктурой.

Django пишет WARNING и выше в stderr, исключения — с traceback.
Сбор и ротацию stderr и журналов Gunicorn обеспечивает площадка.

## Проверка развёртывания

`make -f Makefile.prod check` выполняет диагностику MySQL и
`check --deploy --fail-level WARNING`. Проверьте также:

- внешний HTTPS, редирект, HSTS и Secure-cookie;
- вход в `/admin/`, страницы, переводы и статику;
- загрузку публичных изображений и скачивание учебных материалов;
- отказ анонимному пользователю для внутренних материалов и отсутствие
  прямой раздачи закрытого хранилища;
- поступление ошибок в журналирование.

### Диагностика MySQL перед миграциями и запуском

```sh
make -f Makefile.prod check-mysql
.venv/bin/python manage.py check_mysql --verbosity 2
```

Команда проверяет подключение и метаданные без изменения схемы.
Ошибки блокируют выполнение, предупреждения допускают продолжение.
Диагностика встроена в `check`, `migrate` и `gunicorn-run`;
наличие всех DDL-прав и успешность миграций она не подтверждает.

При несовместимой версии, недоступных InnoDB/collation, недостаточном бюджете
индексов, запрете сессионных настроек или DDL требуется участие администратора.
То же относится к недоступности БД из Jail, несовместимым аутентификации/TLS
и нехватке соединений. Детали подключения проверяются из окружения службы;
параметры приложения исправляются в `DATABASE_URL`, инфраструктурные политики —
на площадке.

## Обновление, резервное копирование и откат

1. Установите новый релиз в отдельный каталог; выполните `check`
   и `check-migrations` с серверным окружением.
2. Остановите все источники записи. Сохраните согласованную копию БД,
   `MEDIA_ROOT` и `PRIVATE_PUBLICATIONS_ROOT`, отдельно — секреты и конфигурацию.
   Для БД используйте принятый на площадке MySQL backup/restore.
3. Выполните `migrate` и `collectstatic` из нового релиза.
4. Переключите службу и статику, запустите приложение и выполните проверки.

DDL MySQL не имеет общего транзакционного отката. После частично выполненной
миграции установите состояние схемы и `showmigrations`; затем восстановите
согласованную копию либо примените проверенное исправление. Повторный запуск
миграций без анализа состояния не заменяет восстановление.

Возврат к предыдущему коду допустим только при совместимости с новой схемой.
Иначе остановите запись, восстановите БД и оба хранилища из одной согласованной
копии, верните прежний релиз и окружение, выполните `collectstatic` и проверки.
Сохраняйте предыдущий релиз до завершения проверки обновления.

## Справочник эксплуатационных команд

`Makefile.prod` совместим с make FreeBSD, использует `.venv/bin/python`;
замена: `PYTHON=/path/to/python`. Серверные цели требуют `DEBUG=False`.

| Цель | Действие |
| --- | --- |
| `check` | MySQL и проверки безопасности Django |
| `check-mysql` | Совместимость подключения MySQL |
| `check-migrations` | Соответствие моделей миграциям |
| `show-migrations` | Состояние миграций |
| `migrate` | Применить миграции |
| `collectstatic` | Собрать статику |
| `create-superuser` | Создать администратора |
| `gunicorn-run` | Проверить MySQL и запустить Gunicorn |

Запуск: `make -f Makefile.prod <цель>`. Для смены пароля:
`.venv/bin/python manage.py changepassword <логин>`.

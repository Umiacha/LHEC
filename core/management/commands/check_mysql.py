"""Read-only preflight for this project's MySQL schema and connection policy."""
import re

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection

# Largest current key: project bigint + (name 255 + organization 500) * utf8mb4.
REQUIRED_INDEX_BYTES = 3028
REQUIRED_COLLATIONS = {'utf8mb4_0900_ai_ci', 'utf8mb4_0900_as_ci', 'utf8mb4_0900_bin'}


def inspect_configuration(version, comment, variables, engines, collations):
    """Return actionable errors and non-blocking warnings, without exposing settings."""
    errors, warnings = [], []
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)', version)
    if 'mariadb' in (version + comment).lower():
        errors.append('MariaDB не проверена для этой схемы. Предоставьте совместимую БД MySQL.')
    elif not match or tuple(map(int, match.groups())) < (8, 0, 16):
        errors.append('Нужен MySQL >= 8.0.16 с исполняемыми CHECK. Обновите сервер или предоставьте совместимую БД.')
    elif tuple(map(int, match.groups())) != (8, 0, 46):
        warnings.append('Локально проверен MySQL 8.0.46; эта версия требует проверки миграций на отдельной БД.')
    modes = set(variables.get('sql_mode', '').upper().split(','))
    if not modes & {'STRICT_TRANS_TABLES', 'STRICT_ALL_TABLES'} or 'NO_ENGINE_SUBSTITUTION' not in modes:
        errors.append('Нет строгого SQL-режима или NO_ENGINE_SUBSTITUTION. Разрешите init_command приложения для сессии.')
    if variables.get('transaction_isolation', '').upper().replace(' ', '-') != 'READ-COMMITTED':
        errors.append('Изоляция сессии должна быть READ COMMITTED. Проверьте OPTIONS и разрешение сессионных настроек.')
    for name in ('character_set_client', 'character_set_connection', 'character_set_results'):
        if variables.get(name) != 'utf8mb4':
            errors.append(f'{name} должна быть utf8mb4. Проверьте charset соединения приложения.')
    missing = REQUIRED_COLLATIONS - collations
    if missing:
        errors.append('Недоступны collation: ' + ', '.join(sorted(missing)) + '. Предоставьте MySQL с этими collation.')
    if engines.get('innodb', '').upper() not in {'YES', 'DEFAULT'}:
        errors.append('InnoDB недоступен. Администратор должен предоставить БД с работающим InnoDB.')
    if variables.get('default_storage_engine', '').lower() != 'innodb':
        errors.append('Сессионный движок не InnoDB. Проверьте разрешение init_command приложения.')
    try:
        page_size = int(variables.get('innodb_page_size', '0'))
    except ValueError:
        page_size = 0
    budget = min(3072, page_size * 3 // 16)
    if page_size not in {4096, 8192, 16384, 32768, 65536} or budget < REQUIRED_INDEX_BYTES:
        errors.append(f'Бюджет индекса {budget} байт, требуется {REQUIRED_INDEX_BYTES} для DYNAMIC. '
                      'Администратор должен предоставить экземпляр InnoDB со страницей не менее 16384 байт.')
    if variables.get('innodb_read_only', '').upper() in {'ON', '1'} or any(variables.get(key, '').upper() in {'ON', '1'} for key in ('read_only', 'super_read_only')):
        errors.append('Сервер работает в read-only. Используйте доступный для записи основной сервер.')
    if variables.get('innodb_default_row_format', '').lower() != 'dynamic':
        warnings.append('Формат строк по умолчанию не DYNAMIC; новые таблицы приложения явно задают DYNAMIC.')
    if variables.get('character_set_database') != 'utf8mb4' or variables.get('collation_database') != 'utf8mb4_0900_ai_ci':
        warnings.append('Кодировка/collation БД по умолчанию отличаются от приложения; новые таблицы задают их явно.')
    if variables.get('collation_connection') not in REQUIRED_COLLATIONS:
        warnings.append('Collation соединения отличается от правил полей; сравнения столбцов используют их явные collation.')
    return errors, warnings


class Command(BaseCommand):
    help = 'Проверить совместимость MySQL без изменения схемы и глобальных настроек.'
    requires_system_checks = []

    def handle(self, *args, **options):
        if connection.vendor != 'mysql':
            raise CommandError('Требуется подключение MySQL. Проверьте DATABASE_URL (значение скрыто).')
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT VERSION(), @@version_comment')
                version, comment = cursor.fetchone()
                cursor.execute('SHOW SESSION VARIABLES WHERE Variable_name IN (' + ', '.join(['%s'] * 15) + ')', [
                    'sql_mode', 'transaction_isolation', 'character_set_client',
                    'character_set_connection', 'character_set_results', 'collation_connection',
                    'character_set_database', 'collation_database', 'default_storage_engine',
                    'innodb_page_size', 'innodb_default_row_format', 'innodb_strict_mode',
                    'innodb_read_only', 'read_only', 'super_read_only',
                ])
                variables = dict(cursor.fetchall())
                cursor.execute('SHOW ENGINES')
                engines = {row[0].lower(): row[1] for row in cursor.fetchall()}
                cursor.execute('SHOW COLLATION WHERE Collation IN (%s, %s, %s)', sorted(REQUIRED_COLLATIONS))
                collations = {row[0] for row in cursor.fetchall()}
        except (DatabaseError, ImproperlyConfigured, ImportError, OSError) as exc:
            # Driver errors can contain credentials, hosts and connection URLs.
            code = exc.args[0] if exc.args and isinstance(exc.args[0], int) else None
            action = {
                1045: 'Проверьте учётные данные, разрешённый источник подключения и способ аутентификации.',
                1044: 'Проверьте права пользователя на выбранную БД.',
                1049: 'Администратор должен создать именованную БД из DATABASE_URL.',
                2002: 'Проверьте доступность Unix-сокета внутри окружения приложения.',
                2003: 'Проверьте адрес, порт, доступность MySQL и сетевые ограничения.',
                2026: 'Проверьте требования TLS, сертификаты и доступность их файлов.',
            }.get(code, 'Нужен MySQL >= 8.0.16 и совместимый драйвер/Django. Проверьте подключение, права чтения метаданных и разрешение сессионных настроек.')
            raise CommandError(f'Диагностика MySQL не выполнена (код {code or "скрыт"}). {action}') from None
        errors, warnings = inspect_configuration(version, comment, variables, engines, collations)
        if options['verbosity'] >= 2:
            self.stdout.write(f'Сервер: {version}; тип: {"MariaDB" if "mariadb" in (version + comment).lower() else "MySQL"}')
            for key, value in sorted(variables.items()):
                self.stdout.write(f'{key}: {value}')
            self.stdout.write('InnoDB: ' + engines.get('innodb', 'NO'))
            self.stdout.write('Collation: ' + ', '.join(sorted(collations)))
        for warning in warnings:
            self.stdout.write(self.style.WARNING('ПРЕДУПРЕЖДЕНИЕ: ' + warning))
        if errors:
            raise CommandError('\n'.join(errors))
        self.stdout.write(self.style.SUCCESS('MySQL: обязательные проверки пройдены.'))

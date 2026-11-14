"""Explicit local MySQL development commands; never administer arbitrary databases."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

import dj_database_url
from dotenv import load_dotenv
import MySQLdb

ROOT = Path(__file__).resolve().parent.parent
DATABASE = 'lhecdev'
USER = 'lhec_dev'
SOCKET = Path('/run/mysqld/mysqld.sock')
DDL = 'CREATE DATABASE IF NOT EXISTS `lhecdev` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci'


def connection_options():
    load_dotenv(ROOT / '.env')
    try:
        config = dj_database_url.parse(os.environ.get('DATABASE_URL', ''))
    except (ValueError, KeyError):
        raise SystemExit('Некорректный DATABASE_URL (значение скрыто).') from None
    host = config.get('HOST', '')
    socket_host = host.startswith('/')
    if (
        config.get('ENGINE') != 'django.db.backends.mysql'
        or config.get('NAME') != DATABASE
        or config.get('USER') != USER
        or config.get('OPTIONS')
        or (socket_host and Path(host).resolve() != SOCKET.resolve())
        or (not socket_host and host not in ('127.0.0.1', 'localhost', '::1'))
        or str(config.get('PORT') or '3306') != '3306'
    ):
        raise SystemExit(
            'Отказ: нужен DATABASE_URL выделенной локальной MySQL-БД lhecdev, '
            'пользователь lhec_dev, порт 3306 или /run/mysqld/mysqld.sock; '
            'дополнительные параметры URL запрещены.'
        )
    options = dict(user=USER, passwd=config.get('PASSWORD', ''), charset='utf8mb4', connect_timeout=5)
    if socket_host or host == 'localhost':
        options['unix_socket'] = str(SOCKET)
    else:
        options.update(host=host, port=3306)
    return options


def connect(options, database=True):
    connection = MySQLdb.connect(**options, **({'db': DATABASE} if database else {}))
    connection.autocommit(True)
    return connection


def prepare(options):
    # No CREATE USER, GRANT or SET GLOBAL: provisioning rights belong to the administrator.
    connection = connect(options, database=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute(DDL)
    finally:
        connection.close()
    print('Dev-БД lhecdev подготовлена. Для миграций: make migrate.')


def reset(options):
    connection = connect(options)
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT DATABASE(), CURRENT_USER(), VERSION()')
            database, user, version = cursor.fetchone()
            if database != DATABASE or user.split('@', 1)[0] != USER or 'mariadb' in version.lower():
                raise SystemExit('Отказ: подключение не соответствует выделенной dev-БД MySQL.')
            try:
                confirmation = input('Удалить ВСЕ данные dev-БД lhecdev? Введите lhecdev: ')
            except EOFError:
                raise SystemExit('Сброс отменён: требуется интерактивное подтверждение.') from None
            if confirmation != DATABASE:
                raise SystemExit('Сброс отменён.')
            cursor.execute('DROP DATABASE `lhecdev`')
            cursor.execute(DDL)
    finally:
        connection.close()
    # A fresh process receives the validated target, never a newly read .env target.
    from urllib.parse import quote
    host = options.get('unix_socket', options.get('host', ''))
    encoded_host = quote(host, safe='') if host.startswith('/') else (
        '[::1]' if host == '::1' else host
    )
    url = f"mysql://{USER}:{quote(options['passwd'], safe='')}@{encoded_host}/{DATABASE}"
    environment = dict(os.environ, DATABASE_URL=url, DJANGO_SETTINGS_MODULE='config.settings')
    subprocess.run(
        [sys.executable, str(ROOT / 'manage.py'), 'migrate', '--noinput'],
        cwd=ROOT, env=environment, check=True,
    )
    print('Dev-БД пересоздана, миграции применены. Файлы media не удалялись.')


def service(action):
    if not Path('/run/systemd/system').is_dir():
        raise SystemExit('systemd недоступен. Управляйте MySQL средствами вашей системы.')
    if action == 'stop':
        try:
            confirmation = input('Остановится ОБЩАЯ служба MySQL. Введите mysql: ')
        except EOFError:
            confirmation = ''
        if confirmation != 'mysql':
            raise SystemExit('Остановка отменена.')
    subprocess.run(['sudo', 'systemctl', action, 'mysql.service'], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'check', 'start', 'stop', 'status', 'reset'))
    action = parser.parse_args().action
    if action in ('start', 'stop'):
        service(action)
        return
    if action == 'status':
        result = subprocess.run(['systemctl', 'is-active', 'mysql.service'], check=False)
        print(f'Код состояния службы: {result.returncode}. Проверяю dev-подключение…', flush=True)
    options = connection_options()
    if action == 'prepare':
        prepare(options)
    elif action == 'reset':
        reset(options)
    else:
        connection = connect(options)
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
        finally:
            connection.close()
        print('Подключение к dev-БД lhecdev доступно. Совместимость: make check-mysql.')


if __name__ == '__main__':
    try:
        main()
    except MySQLdb.Error as error:
        code = error.args[0] if error.args and isinstance(error.args[0], int) else 'скрыт'
        raise SystemExit(f'Ошибка MySQL (код {code}). Проверьте службу, учётные данные и права; секреты скрыты.') from None
    except (subprocess.CalledProcessError, OSError):
        raise SystemExit('Не удалось выполнить локальную команду. Проверьте systemd, sudo и доступность MySQL.') from None

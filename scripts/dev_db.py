"""Manage only this checkout's disposable, socket-only PostgreSQL cluster."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlencode

import psycopg


ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / '.local' / 'postgres'
DATA = BASE / 'data'
SOCKET = BASE / 'socket'
ROLE = 'lhec_dev'
DATABASE = 'lhec_dev'
URL = f'postgresql://{ROLE}@/{DATABASE}?' + urlencode({'host': str(SOCKET)})


def binary(name):
    directory = os.environ.get('PG_BINDIR')
    if directory:
        candidate = Path(directory) / name
    elif shutil.which(name):
        return shutil.which(name)
    elif shutil.which('pg_config'):
        directory = subprocess.check_output(['pg_config', '--bindir'], text=True).strip()
        candidate = Path(directory) / name
    else:
        raise SystemExit('Установите сервер PostgreSQL и задайте PG_BINDIR при необходимости.')
    if not candidate.is_file():
        raise SystemExit(f'Не найден {candidate}. Нужен сервер PostgreSQL, не только клиент.')
    return str(candidate)


def running():
    if not (DATA / 'PG_VERSION').exists():
        return False
    result = subprocess.run(
        [binary('pg_ctl'), '-D', str(DATA), 'status'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if result.returncode not in (0, 3):
        raise SystemExit('Не удалось определить состояние локального PostgreSQL.')
    return result.returncode == 0


def admin_connection():
    connection = psycopg.connect(
        host=str(SOCKET), port=5432, user=ROLE, dbname='postgres',
        connect_timeout=5, autocommit=True,
    )
    actual = connection.execute('SHOW data_directory').fetchone()[0]
    if Path(actual).resolve() != DATA.resolve():
        connection.close()
        raise SystemExit('Отказ: сокет принадлежит другому кластеру PostgreSQL.')
    return connection


def start():
    if os.geteuid() == 0:
        raise SystemExit('Запускайте dev-БД от обычного пользователя, не root.')
    BASE.mkdir(parents=True, exist_ok=True, mode=0o700)
    BASE.chmod(0o700)
    SOCKET.mkdir(exist_ok=True, mode=0o700)
    SOCKET.chmod(0o700)
    if not (DATA / 'PG_VERSION').exists():
        subprocess.run([
            binary('initdb'), '-D', str(DATA), '--username', ROLE,
            '--encoding=UTF8', '--locale=C', '--auth-local=trust', '--auth-host=reject',
        ], check=True)
        with (DATA / 'postgresql.conf').open('a') as config:
            socket_path = str(SOCKET).replace("'", "''")
            config.write(
                f"\nlisten_addresses = ''\nunix_socket_directories = '{socket_path}'\n"
                "unix_socket_permissions = 0700\nport = 5432\n"
                "max_connections = 20\nshared_buffers = '32MB'\n"
            )
    if not running():
        subprocess.run([
            binary('pg_ctl'), '-D', str(DATA), '-l', str(BASE / 'server.log'),
            '-w', '-t', '30', 'start',
        ], check=True)
    with admin_connection() as connection:
        if not connection.execute(
            'SELECT 1 FROM pg_database WHERE datname = %s', (DATABASE,),
        ).fetchone():
            connection.execute('CREATE DATABASE lhec_dev OWNER lhec_dev')
    print(f'Локальный PostgreSQL готов. Для .env:\nDATABASE_URL={URL}')


def reset():
    if input('Удалить ВСЕ данные локальной dev-БД? Введите lhec_dev: ') != DATABASE:
        raise SystemExit('Сброс отменён.')
    start()
    with admin_connection() as connection:
        connection.execute('DROP DATABASE lhec_dev WITH (FORCE)')
        connection.execute('CREATE DATABASE lhec_dev OWNER lhec_dev')
    # Target our own cluster even if .env points at production.
    environment = dict(os.environ, DATABASE_URL=URL)
    subprocess.run(
        [sys.executable, str(ROOT / 'manage.py'), 'migrate', '--noinput'],
        cwd=ROOT, env=environment, check=True,
    )
    print('Dev-БД пересоздана, миграции применены. Файлы media не удалялись.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'stop', 'status', 'reset'))
    action = parser.parse_args().action
    if action == 'start':
        start()
    elif action == 'reset':
        reset()
    elif action == 'status':
        print('Локальный PostgreSQL запущен.' if running() else 'Локальный PostgreSQL остановлен.')
    elif running():
        subprocess.run([
            binary('pg_ctl'), '-D', str(DATA), '-m', 'fast', '-w', '-t', '30', 'stop',
        ], check=True)


if __name__ == '__main__':
    try:
        main()
    except (subprocess.CalledProcessError, psycopg.Error, OSError) as error:
        raise SystemExit(f'Ошибка локального PostgreSQL: {error}') from None

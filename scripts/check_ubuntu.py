"""Reproduce the Ubuntu source-checkout checks against an isolated MySQL test DB."""
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from dev_db import connection_options

ROOT = Path(__file__).resolve().parent.parent


def main():
    connection_options()  # Reject remote/production targets before invoking Django.
    with TemporaryDirectory(prefix='lhec-ubuntu-') as temporary:
        environment = dict(
            os.environ, DJANGO_SETTINGS_MODULE='config.settings',
            DJANGO_DEBUG='False', DJANGO_ALLOWED_HOSTS='localhost,127.0.0.1,testserver',
            DJANGO_SECURE_SSL_REDIRECT='False', DJANGO_SESSION_COOKIE_SECURE='False',
            DJANGO_CSRF_COOKIE_SECURE='False', DJANGO_SERVE_STATIC='True',
            STATIC_ROOT=str(Path(temporary) / 'static'),
            MEDIA_ROOT=str(Path(temporary) / 'media'),
            PRIVATE_PUBLICATIONS_ROOT=str(Path(temporary) / 'private'),
            LHEC_HTTP_SMOKE='1',
        )
        commands = [
            ['npm', 'run', 'css:build'],
            [sys.executable, 'manage.py', 'collectstatic', '--noinput'],
            [sys.executable, 'manage.py', 'check_mysql'],
            [sys.executable, 'manage.py', 'check'],
            [sys.executable, 'manage.py', 'makemigrations', '--check', '--dry-run'],
            # Interactive runner refuses to overwrite an existing test_lhecdev in unattended runs.
            # No --noinput, --keepdb or production migrate here.
            [sys.executable, 'manage.py', 'test', '--verbosity', '2'],
        ]
        for command in commands:
            print('>>> ' + ' '.join(command), flush=True)
            subprocess.run(command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL, check=True)
    print('Ubuntu: checks, fresh migrations, tests and both HTTP servers passed.')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit('Проверка Ubuntu не пройдена; см. вывод команды выше.') from None

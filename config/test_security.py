"""Environment and HTTPS contract; no database or running proxy required."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class SecurityEnvironmentTests(unittest.TestCase):
    def run_python(self, code, **overrides):
        env = {k: v for k, v in os.environ.items() if not k.startswith('DJANGO_')}
        env.update(
            PYTHON_DOTENV_DISABLED='1',
            DJANGO_SETTINGS_MODULE='config.settings',
            DJANGO_SECRET_KEY='test-only-' + 'abcdefghijklmnopqrstuvwxyz0123456789' * 2,
            DATABASE_URL='postgresql://test@localhost/test',
        )
        env.update(overrides)
        return subprocess.run(
            [sys.executable, '-c', code], env=env, capture_output=True,
            text=True, cwd=Path(__file__).resolve().parent.parent,
        )

    def test_defaults_do_not_trust_forwarded_header(self):
        result = self.run_python('''
from django.conf import settings
from django.test import RequestFactory
assert not settings.SESSION_COOKIE_SECURE
assert not settings.CSRF_COOKIE_SECURE
assert not settings.SECURE_SSL_REDIRECT
assert settings.SECURE_HSTS_SECONDS == 0
assert not RequestFactory().get('/', HTTP_X_FORWARDED_PROTO='https').is_secure()
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_check_and_https_behavior(self):
        result = self.run_python('''
import django
django.setup()
from django.core.management import call_command
from django.http import HttpResponse
from django.middleware.security import SecurityMiddleware
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
call_command('check', deploy=True, fail_level='WARNING')
factory = RequestFactory()
middleware = SecurityMiddleware(lambda request: HttpResponse('ok'))
response = middleware(factory.get('/path/?a=1', HTTP_HOST='example.org'))
assert response.status_code == 301
assert response['Location'] == 'https://example.org/path/?a=1'
request = factory.get('/', HTTP_HOST='example.org', HTTP_X_FORWARDED_PROTO='https')
assert request.is_secure()
response = middleware(request)
assert response.status_code == 200
assert response['Strict-Transport-Security'] == 'max-age=300'
csrf = CsrfViewMiddleware(lambda request: HttpResponse())
get_token(request)
response = csrf.process_response(request, HttpResponse())
assert response.cookies['csrftoken']['secure']
# Signed-cookie backend avoids a database while exercising SessionMiddleware.
from django.test import override_settings
with override_settings(SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies'):
    sessions = SessionMiddleware(lambda request: HttpResponse())
    sessions.process_request(request)
    request.session['test'] = 'value'
    response = sessions.process_response(request, HttpResponse())
    assert response.cookies['sessionid']['secure']
''', DJANGO_ALLOWED_HOSTS='example.org', DJANGO_SESSION_COOKIE_SECURE='True',
            DJANGO_CSRF_COOKIE_SECURE='1', DJANGO_SECURE_SSL_REDIRECT='true',
            DJANGO_TRUST_PROXY_SSL_HEADER='True', DJANGO_SECURE_HSTS_SECONDS='300',
            DJANGO_SILENCED_SECURITY_CHECKS='security.W005,security.W021')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_configuration_fails_closed(self):
        for name, value in (
            ('DJANGO_SESSION_COOKIE_SECURE', 'typo'),
            ('DJANGO_TRUST_PROXY_SSL_HEADER', 'yes'),
            ('DJANGO_SECURE_HSTS_SECONDS', '-1'),
            ('DJANGO_SECURE_HSTS_SECONDS', 'abc'),
            ('DJANGO_SILENCED_SECURITY_CHECKS', 'security.W012'),
        ):
            with self.subTest(name=name, value=value):
                result = self.run_python('from django.conf import settings; settings.SECURE_SSL_REDIRECT', **{name: value})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('ImproperlyConfigured', result.stderr)
                self.assertIn(name, result.stderr)

"""Real HTTP checks on both application servers, enabled by make check-ubuntu."""
import http.cookiejar
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.templatetags.static import static
from django.test import TransactionTestCase
from django.urls import reverse

from publications.models import Publication, PublicationFile
from research.models import ResearchDirection

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(os.environ.get('LHEC_HTTP_SMOKE') == '1', 'Use make check-ubuntu for real HTTP checks')
class HttpServerSmokeTests(TransactionTestCase):
    def test_runserver_and_gunicorn(self):
        # External workers must see committed data; never run against the regular dev DB.
        self.assertEqual(connection.settings_dict['NAME'], 'test_lhecdev')
        password = secrets.token_urlsafe(24)
        get_user_model().objects.create_superuser('ubuntu-smoke', password=password)
        publication = Publication.objects.create(
            title='Ubuntu smoke publication', authors_text='Smoke author', year=2026, is_published=True,
        )
        attachment = PublicationFile.objects.create(
            publication=publication, file=SimpleUploadedFile('smoke.pdf', b'%PDF-smoke'),
        )
        self.assertTrue(Path(attachment.file.path).is_relative_to(settings.PRIVATE_PUBLICATIONS_ROOT))
        config = connection.settings_dict
        host = config.get('HOST') or 'localhost'
        encoded_host = quote(host, safe='') if host.startswith('/') else ('[::1]' if host == '::1' else host)
        port = ':' + str(config['PORT']) if config.get('PORT') else ''
        url = (f"mysql://{quote(config['USER'], safe='')}:{quote(config['PASSWORD'], safe='')}"
               f"@{encoded_host}{port}/test_lhecdev")
        environment = dict(os.environ, DATABASE_URL=url, DJANGO_SETTINGS_MODULE='config.settings')
        for server in ('runserver', 'gunicorn'):
            with self.subTest(server=server):
                self.check_server(server, environment, password, attachment)

    def check_server(self, server, environment, password, attachment):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        address = f'127.0.0.1:{port}'
        base = f'http://{address}'
        command = ([sys.executable, 'manage.py', 'runserver', address, '--noreload']
                   if server == 'runserver' else
                   [sys.executable, '-m', 'gunicorn', 'config.wsgi:application',
                    '--bind', address, '--workers', '1', '--access-logfile', '-'])
        with tempfile.TemporaryFile(mode='w+') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=log, stderr=log)
            try:
                browser = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

                def request(path, data=None):
                    payload = urlencode(data).encode() if data is not None else None
                    try:
                        response = browser.open(Request(base + path, data=payload), timeout=5)
                    except HTTPError as response:
                        return response.code, response.read(), response.geturl()
                    with response:
                        return response.status, response.read(), response.geturl()

                deadline = time.monotonic() + 25
                while True:
                    try:
                        status, body, _ = request('/')
                        self.assertEqual(status, 200)
                        break
                    except (URLError, TimeoutError):
                        if process.poll() is not None or time.monotonic() > deadline:
                            self.fail(f'{server} did not start')
                        time.sleep(0.2)

                self.assertEqual(request(static('core/css/main.css'))[0], 200)
                self.assertEqual(request(attachment.file.url)[0], 403)
                self.assertEqual(request('/media/' + attachment.file.name)[0], 404)

                def post_form(path, data):
                    status, body, _ = request(path)
                    self.assertEqual(status, 200)
                    token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', body)
                    self.assertIsNotNone(token)
                    return request(path, dict(data, csrfmiddlewaretoken=token[1].decode()))

                status, body, location = post_form('/admin/login/?next=/admin/', {
                    'username': 'ubuntu-smoke', 'password': password, 'next': '/admin/',
                })
                self.assertEqual(status, 200)
                self.assertEqual(location, base + '/admin/')
                self.assertEqual(request(attachment.file.url)[:2], (200, b'%PDF-smoke'))
                search = reverse('publications:publications') + '?q=Ubuntu'
                self.assertIn(b'Ubuntu smoke publication', request(search)[1])

                # Exercise create/read/search/update/delete through actual CSRF-protected admin forms.
                name = 'HTTP smoke ' + server
                form = {
                    'name': name, 'slug': 'http-smoke-' + server,
                    'sort_order': '0', 'is_published': 'on', '_save': 'Save',
                    'memberships-TOTAL_FORMS': '0', 'memberships-INITIAL_FORMS': '0',
                    'memberships-MIN_NUM_FORMS': '0', 'memberships-MAX_NUM_FORMS': '1000',
                }
                self.assertEqual(post_form('/admin/research/researchdirection/add/', form)[0], 200)
                direction = ResearchDirection.objects.get(name=name)
                change = f'/admin/research/researchdirection/{direction.pk}/change/'
                self.assertIn(name.encode(), request(change)[1])
                self.assertIn(name.encode(), request('/admin/research/researchdirection/?' + urlencode({'q': name}))[1])
                self.assertEqual(post_form(change, dict(form, name=name + ' updated'))[0], 200)
                direction.refresh_from_db()
                self.assertEqual(direction.name, name + ' updated')
                self.assertEqual(post_form(f'/admin/research/researchdirection/{direction.pk}/delete/', {'post': 'yes'})[0], 200)
                self.assertFalse(ResearchDirection.objects.filter(pk=direction.pk).exists())
                print(f'HTTP {server} {base}: pages/static/login/CRUD/search/private files OK', flush=True)
            except Exception:
                log.seek(0)
                print(log.read(), flush=True)
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

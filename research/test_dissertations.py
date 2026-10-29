from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from users.roles import EMPLOYEE_GROUP_NAME
from .models import Dissertation


class DissertationTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = override_settings(
            PRIVATE_PUBLICATIONS_ROOT=directory.name,
            STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
            },
        )
        settings.enable()
        self.addCleanup(settings.disable)
        self.dissertation = Dissertation.objects.create(
            title='Название диссертации', author='Иванов Иван', year=2021,
            specialty='02.00.09 — Химия высоких энергий', supervisors='Руководитель',
            external_url='https://example.org/thesis/', is_published=True,
            file=SimpleUploadedFile('thesis.pdf', b'%PDF-thesis'),
        )
        self.url = self.dissertation.file.url
        self.page = reverse('core:science')
        self.employee = get_user_model().objects.create_user(username='employee')
        self.employee.groups.add(Group.objects.get(name=EMPLOYEE_GROUP_NAME))

    def test_file_directory_uses_defense_year(self):
        self.assertEqual(self.dissertation.file.name, 'dissertations/2021/thesis.pdf')

    def test_public_card_links_to_source_and_hides_download(self):
        response = self.client.get(self.page)
        for value in ('Название диссертации', 'Иванов Иван', '2021', 'Руководитель', self.dissertation.external_url):
            self.assertContains(response, value)
        self.assertNotContains(response, self.url)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertFalse(Path(self.dissertation.file.path).is_relative_to(Path('media').resolve()))

    def test_login_and_staff_flag_alone_do_not_grant_access(self):
        for staff in (False, True):
            user = get_user_model().objects.create_user(username=f'user{staff}', is_staff=staff)
            self.client.force_login(user)
            self.assertNotContains(self.client.get(self.page), self.url)
            self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_employee_and_administrator_can_download(self):
        admin = get_user_model().objects.create_superuser(username='admin', password='password')
        for user in (self.employee, admin):
            self.client.force_login(user)
            self.assertContains(self.client.get(self.page), self.url)
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('attachment;', response['Content-Disposition'])
            self.assertIn('private', response['Cache-Control'])
            self.assertEqual(b''.join(response.streaming_content), b'%PDF-thesis')
            response.close()

    def test_unpublished_and_missing_files(self):
        self.client.force_login(self.employee)
        self.dissertation.is_published = False
        self.dissertation.save()
        self.assertNotContains(self.client.get(self.page), self.dissertation.title)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.dissertation.is_published = True
        self.dissertation.save()
        Path(self.dissertation.file.path).unlink()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.dissertation.file = ''
        self.dissertation.save()
        self.assertNotContains(self.client.get(self.page), 'Скачать диссертацию')

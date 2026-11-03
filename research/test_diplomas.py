from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse

from users.models import Employee
from users.roles import EMPLOYEE_GROUP_NAME
from .models import Diploma


class DiplomaTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = override_settings(PRIVATE_PUBLICATIONS_ROOT=directory.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.author = Employee.objects.create(first_name='Иван', last_name='Иванов')
        self.diploma = Diploma.objects.create(
            title='Диплом', author=self.author, year=2020, level=Diploma.Level.SPECIALIST,
            external_url='https://example.org/diploma', is_published=True,
            file=SimpleUploadedFile('diploma.pdf', b'%PDF-diploma'),
        )
        self.url = self.diploma.file.url

    def test_file_path_and_author_protection(self):
        self.assertEqual(self.diploma.file.name, 'diplomas/2020/diploma.pdf')
        from django.conf import settings
        self.assertFalse(Path(self.diploma.file.path).is_relative_to(settings.MEDIA_ROOT))
        with self.assertRaises(ProtectedError):
            self.author.delete()

    def test_permissions(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)
        user = get_user_model().objects.create_user(username='staff', is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        user.groups.add(Group.objects.get(name=EMPLOYEE_GROUP_NAME))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('private', response['Cache-Control'])
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertEqual(b''.join(response.streaming_content), b'%PDF-diploma')

    def test_missing_and_unpublished_file(self):
        user = get_user_model().objects.create_superuser(username='admin', password='password')
        self.client.force_login(user)
        self.diploma.is_published = False
        self.diploma.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.diploma.is_published = True
        self.diploma.save()
        Path(self.diploma.file.path).unlink()
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_admin_can_create_without_file(self):
        user = get_user_model().objects.create_superuser(username='admin', password='password')
        self.client.force_login(user)
        response = self.client.post(reverse('admin:research_diploma_add'), {
            'title': 'Новая ВКР', 'external_url': 'https://example.org/new',
            'author': self.author.pk, 'year': 2021, 'level': Diploma.Level.MASTER,
            'supervisors': [self.author.pk], 'external_supervisors': 'Внешний руководитель',
            'sort_order': 0, '_save': 'Сохранить',
        })
        self.assertEqual(response.status_code, 302)
        diploma = Diploma.objects.get(title='Новая ВКР')
        self.assertFalse(diploma.file)
        self.assertFalse(diploma.is_published)
        self.assertEqual(list(diploma.supervisors.all()), [self.author])

    def test_science_card_and_publication_visibility(self):
        supervisor = Employee.objects.create(first_name='Пётр', last_name='Петров', is_published=False)
        self.diploma.supervisors.add(supervisor)
        self.diploma.external_supervisors = 'Внешний руководитель'
        self.diploma.save()
        page = reverse('core:science')
        response = self.client.get(page)
        self.assertContains(response, self.diploma.external_url)
        self.assertContains(response, self.diploma.get_level_display())
        self.assertContains(response, reverse('users:employe_card', args=[self.author.pk]))
        self.assertContains(response, 'Внешний руководитель')
        self.assertContains(response, 'Петров')
        self.assertNotContains(response, reverse('users:employe_card', args=[supervisor.pk]))
        self.assertNotContains(response, self.url)
        self.assertLess(response.content.index(b'id="dissertations"'), response.content.index(b'id="diplomas"'))
        self.author.is_published = False
        self.author.save()
        self.assertNotContains(self.client.get(page), reverse('users:employe_card', args=[self.author.pk]))
        self.diploma.is_published = False
        self.diploma.save()
        self.assertNotContains(self.client.get(page), self.diploma.external_url)

    def test_science_download_requires_employee_and_file(self):
        page = reverse('core:science')
        user = get_user_model().objects.create_user(username='reader', is_staff=True)
        self.client.force_login(user)
        self.assertNotContains(self.client.get(page), self.url)
        user.groups.add(Group.objects.get(name=EMPLOYEE_GROUP_NAME))
        self.assertContains(self.client.get(page), self.url)
        self.diploma.file = ''
        self.diploma.save()
        self.assertNotContains(self.client.get(page), 'Скачать ВКР')

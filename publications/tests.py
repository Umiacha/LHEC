from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from users.roles import EMPLOYEE_GROUP_NAME
from .models import Publication, PublicationFile


class PublicationFileTests(TestCase):
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
        self.publication = Publication.objects.create(
            title='Статья', year=2026, authors_text='Автор', is_published=True,
        )
        self.attachment = PublicationFile.objects.create(
            publication=self.publication,
            file=SimpleUploadedFile('article.pdf', b'%PDF-test'),
        )
        self.url = self.attachment.file.url
        self.card_url = reverse('publications:publication', args=[self.publication.pk])
        self.employee = get_user_model().objects.create_user(username='employee')
        self.employee.groups.add(Group.objects.get(name=EMPLOYEE_GROUP_NAME))

    def test_anonymous_cannot_see_or_download_files(self):
        self.assertNotContains(self.client.get(self.card_url), self.url)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_staff_flag_alone_does_not_grant_access(self):
        user = get_user_model().objects.create_user(username='staff', is_staff=True)
        self.client.force_login(user)
        self.assertNotContains(self.client.get(self.card_url), self.url)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_employee_can_download_multiple_files(self):
        second = PublicationFile.objects.create(
            publication=self.publication,
            file=SimpleUploadedFile('supplement.txt', b'supplement'),
        )
        self.client.force_login(self.employee)
        card = self.client.get(self.card_url)
        for attachment in (self.attachment, second):
            self.assertContains(card, attachment.file.url)
            self.assertContains(card, f'Скачать: {Path(attachment.file.name).name}')
            response = self.client.get(attachment.file.url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('attachment;', response['Content-Disposition'])
            self.assertIn('private', response['Cache-Control'])
            self.assertTrue(b''.join(response.streaming_content))
            response.close()

    def test_administrator_can_download(self):
        admin = get_user_model().objects.create_superuser(username='admin', password='password')
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertEqual(b''.join(response.streaming_content), b'%PDF-test')
        response.close()

    def test_unpublished_article_and_missing_file_return_404(self):
        self.client.force_login(self.employee)
        self.publication.is_published = False
        self.publication.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.publication.is_published = True
        self.publication.save()
        Path(self.attachment.file.path).unlink()
        self.assertEqual(self.client.get(self.url).status_code, 404)

    @override_settings(DEBUG=True)
    def test_file_is_outside_public_media(self):
        from django.conf import settings
        self.assertFalse(Path(self.attachment.file.path).is_relative_to(settings.MEDIA_ROOT))
        self.assertEqual(self.client.get('/media/' + self.attachment.file.name).status_code, 404)

    def test_admin_inline_upload(self):
        admin = get_user_model().objects.create_superuser(username='admin', password='password')
        self.client.force_login(admin)
        response = self.client.post(reverse('admin:publications_publication_add'), {
            'title': 'Новая статья', 'year': 2020, 'authors_text': 'Автор',
            'kind': 'article', 'is_published': 'on',
            'files-TOTAL_FORMS': '1', 'files-INITIAL_FORMS': '0',
            'files-MIN_NUM_FORMS': '0', 'files-MAX_NUM_FORMS': '1000',
            'files-0-file': SimpleUploadedFile('new.pdf', b'%PDF-new'),
            '_save': 'Сохранить',
        })
        self.assertEqual(response.status_code, 302)
        attachment = PublicationFile.objects.get(publication__title='Новая статья')
        self.assertEqual(attachment.file.name, 'publications/2020/new.pdf')
        response = self.client.get(attachment.file.url)
        self.assertEqual(b''.join(response.streaming_content), b'%PDF-new')
        response.close()

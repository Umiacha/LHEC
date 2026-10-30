from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Publication


class AdminImportTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_superuser('admin', password='test'))
        self.url = reverse('admin:publications_publication_add')

    def post_data(self, **extra):
        return {
            'title': 'Title', 'year': '2026', 'authors_text': 'Author', 'kind': 'article',
            'files-TOTAL_FORMS': '1', 'files-INITIAL_FORMS': '0',
            'files-MIN_NUM_FORMS': '0', 'files-MAX_NUM_FORMS': '1000',
            '_save': 'Save', **extra,
        }

    def test_add_page(self):
        self.assertContains(self.client.get(self.url), 'Прочитать файл')

    def test_import_does_not_save_and_preserves_note(self):
        content = (Path(__file__).parent / 'test_data/article.bib').read_bytes()
        response = self.client.post(self.url, self.post_data(
            _import='1', bibliography=SimpleUploadedFile('article.bib', content), note='Keep me',
        ))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Radiation-induced transformations')
        form = response.context['adminform'].form
        self.assertEqual(form.initial['note'], 'Keep me')
        self.assertEqual(form.initial['year'], 2026)
        self.assertFalse(form.initial['is_published'])
        self.assertFalse(form.is_bound)
        self.assertFalse(Publication.objects.exists())

    def test_bad_import_keeps_entered_values(self):
        response = self.client.post(self.url, self.post_data(
            _import='1', bibliography=SimpleUploadedFile('article.ris', b'broken'),
        ))
        self.assertTrue(response.context['import_form'].errors.get('bibliography'))
        self.assertEqual(response.context['adminform'].form.initial['title'], 'Title')
        self.assertFalse(Publication.objects.exists())

    def test_save_requires_confirmation_for_duplicate(self):
        original = Publication.objects.create(title='Title', year=2026, authors_text='Author')
        response = self.client.post(self.url, self.post_data())
        self.assertContains(response, 'Найдены возможные дубли')
        self.assertContains(response, reverse('admin:publications_publication_change', args=[original.pk]))
        self.assertEqual(Publication.objects.count(), 1)
        response = self.client.post(self.url, self.post_data(confirm_duplicate='on'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Publication.objects.count(), 2)

    def test_save_unique_and_edit_self(self):
        self.assertEqual(self.client.post(self.url, self.post_data()).status_code, 302)
        publication = Publication.objects.get()
        url = reverse('admin:publications_publication_change', args=[publication.pk])
        self.assertEqual(self.client.post(url, self.post_data()).status_code, 302)
        self.assertNotContains(self.client.get(url), 'Прочитать файл')

    def test_import_requires_add_permission(self):
        user = get_user_model().objects.create_user('staff', is_staff=True)
        self.client.force_login(user)
        response = self.client.post(self.url, {'_import': '1'})
        self.assertEqual(response.status_code, 403)

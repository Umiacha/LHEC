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

    def test_administrator_can_download(self):
        admin = get_user_model().objects.create_superuser(username='admin', password='password')
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertEqual(b''.join(response.streaming_content), b'%PDF-test')

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


class PublicationSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from research.models import ResearchDirection
        from users.models import Employee

        cls.employee = Employee.objects.create(last_name='Иванов', first_name='Иван')
        cls.direction = ResearchDirection.objects.create(
            name='Радиохимия', slug='radiochemistry', is_published=True,
        )
        cls.paper = Publication.objects.create(
            title='Radiation chemistry', year=2025, authors_text='Ivanov, Smith',
            venue='Chemical Journal', doi='10.1234/example', is_published=True,
        )
        cls.paper.employees.add(cls.employee)
        cls.paper.research_directions.add(cls.direction)
        cls.other = Publication.objects.create(
            title='Other paper', year=2024, authors_text='Petrov', is_published=True,
        )
        cls.hidden = Publication.objects.create(
            title='Radiation draft', year=2026, authors_text='Smith', is_published=False,
        )
        cls.url = reverse('publications:publications')

    def results(self, params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return list(response.context['publications'])

    def test_search_fields_and_whitespace(self):
        for query in ('radiation', 'SMITH', 'chemical journal', '10.1234/example', '  Radiation  '):
            with self.subTest(query=query):
                self.assertEqual(self.results({'q': query}), [self.paper])

    def test_filters_separately_and_together(self):
        params = {
            'employee': self.employee.pk, 'year': 2025,
            'direction': self.direction.pk, 'q': 'Smith',
        }
        for key, value in params.items():
            with self.subTest(field=key):
                self.assertEqual(self.results({key: value}), [self.paper])
        self.assertEqual(self.results(params), [self.paper])
        self.assertEqual(self.results({**params, 'year': 2024}), [])

    def test_default_order_and_publication_visibility(self):
        self.assertEqual(self.results({}), [self.paper, self.other])
        response = self.client.get(self.url)
        self.assertNotContains(response, self.hidden.title)
        self.assertNotIn((2026, 2026), response.context['form'].fields['year'].choices)

    def test_choices_exclude_unpublished_and_unused_relations(self):
        from research.models import ResearchDirection
        from users.models import Employee

        employee = Employee.objects.create(last_name='Скрытый', first_name='Автор', is_published=False)
        direction = ResearchDirection.objects.create(name='Скрытое', slug='hidden')
        self.paper.employees.add(employee)
        self.paper.research_directions.add(direction)
        unused_employee = Employee.objects.create(last_name='Другой', first_name='Автор')
        unused_direction = ResearchDirection.objects.create(name='Другое', slug='unused', is_published=True)
        self.hidden.employees.add(unused_employee)
        self.hidden.research_directions.add(unused_direction)
        form = self.client.get(self.url).context['form']
        self.assertEqual(list(form.fields['employee'].queryset), [self.employee])
        self.assertEqual(list(form.fields['direction'].queryset), [self.direction])

    def test_invalid_filters_show_errors(self):
        for params in ({'year': 'bad'}, {'year': 1900}, {'employee': 99999},
                       {'direction': 'bad'}, {'q': 'x' * 501}):
            with self.subTest(params=params):
                response = self.client.get(self.url, params)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertEqual(list(response.context['publications']), [])
                self.assertContains(response, 'Проверьте параметры поиска')

    def test_no_matches(self):
        response = self.client.get(self.url, {'q': 'no match'})
        self.assertContains(response, 'Публикации не найдены')
        self.assertContains(response, 'Найдено публикаций: 0')

    def test_pagination_preserves_filters_and_selection(self):
        for index in range(21):
            paper = Publication.objects.create(
                title=f'Search & find {index}', year=2025,
                authors_text='Author', is_published=True,
            )
            paper.employees.add(self.employee)
            paper.research_directions.add(self.direction)
        params = {
            'q': 'Search & find', 'employee': self.employee.pk,
            'direction': self.direction.pk, 'year': 2025,
        }
        response = self.client.get(self.url, params)
        self.assertEqual(len(response.context['publications']), 20)
        from urllib.parse import urlencode
        from django.utils.html import escape
        self.assertContains(response, escape('?' + urlencode({**params, 'page': 2})))
        self.assertContains(response, 'value="Search &amp; find"')
        second = self.client.get(self.url, {**params, 'page': 2})
        self.assertEqual(len(second.context['publications']), 1)
        self.assertFalse(set(response.context['publications']) & set(second.context['publications']))
        for page, expected in [('bad', 1), ('999', 2)]:
            self.assertEqual(self.client.get(self.url, {**params, 'page': page}).context['page_obj'].number, expected)


class PublicationReturnLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.publication = Publication.objects.create(
            title='Контекст каталога', year=2026, authors_text='Автор',
            is_published=True,
        )

    def test_catalog_link_preserves_filters_and_page(self):
        catalog = reverse('publications:publications')
        return_to = catalog + '?q=Контекст&page=1'
        response = self.client.get(return_to)
        detail = reverse('publications:publication', args=[self.publication.pk])
        from html import unescape
        self.assertIn(detail + '?return_to=', unescape(response.content.decode()))
        response = self.client.get(detail, {'return_to': return_to})
        self.assertEqual(response.context['return_to'], return_to)
        self.assertIn('href="' + return_to + '"', unescape(response.content.decode()))

    def test_unrelated_or_malformed_return_urls_fall_back_to_catalog(self):
        detail = reverse('publications:publication', args=[self.publication.pk])
        catalog = reverse('publications:publications')
        for value in ('https://example.com' + catalog, '//example.com' + catalog,
                      '/admin/', 'http://[invalid', ''):
            with self.subTest(value=value):
                response = self.client.get(detail, {'return_to': value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['return_to'], '')
                self.assertContains(response, f'href="{catalog}"')

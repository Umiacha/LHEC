from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from publications.importers import (
    PublicationImportError,
    find_duplicates,
    parse_publication,
)
from publications.models import Publication, PublicationFile
from users.roles import EMPLOYEE_GROUP_NAME


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


FIXTURES = Path(__file__).parent / 'test_data'


class ParserTests(SimpleTestCase):
    def test_rsc_publisher_headers(self):
        content = (FIXTURES / 'rsc_article.ris').read_bytes()
        for explicit_format in (None, 'ris'):
            with self.subTest(format=explicit_format):
                result = parse_publication(content, format=explicit_format)
                self.assertEqual(result.source_format, 'ris')
                self.assertEqual(result.errors, {})
                self.assertEqual(result.data['doi'], '10.1039/d3cp02834h')
                self.assertEqual(result.data['year'], 2023)
                self.assertEqual(result.data['pages'], '21883–21896')
                self.assertIn('Pavel V. Zasimov', result.data['authors_text'])
                self.assertNotIn('Provider', result.unmapped_fields)

    def test_ris_headers_do_not_hide_invalid_records(self):
        header = 'Provider: Silverchair\nDatabase: RSC\nContent: text/plain\n\n'
        record = 'TY  - JOUR\nTI  - Title\nER  -\n'
        for text in (header + record * 2, header + 'TY  - JOUR\nTI  - Title',
                     header + 'garbage\n' + record, header + record + 'Provider: Other'):
            with self.subTest(text=text), self.assertRaises(PublicationImportError):
                parse_publication(text, format='ris')

    def test_publisher_exports_match(self):
        results = []
        for extension in ('bib', 'ris'):
            upload = SimpleUploadedFile('article.' + extension, (FIXTURES / ('article.' + extension)).read_bytes())
            result = parse_publication(upload)
            self.assertEqual(result.errors, {})
            self.assertEqual(result.data['year'], 2026)
            self.assertEqual(result.data['doi'], '10.1016/j.radphyschem.2025.113557')
            self.assertEqual(result.data['pages'], '113557')
            self.assertFalse(result.data['is_published'])
            self.assertIn('Vladimir S. Sulaev', result.data['authors_text'])
            self.assertTrue(result.unmapped_fields)
            results.append(result.data)
        self.assertEqual(*results)

    def test_latex_names_strings_and_unicode(self):
        result = parse_publication(r'''@string{journalname = "Журнал"}
@article{key, title={An {FTIR} study of {\"o} and \&},
 author={Иванов, Иван and {Research and Development Team}},
 year=2025, journal=journalname, pages={1--12}}''')
        self.assertEqual(result.errors, {})
        self.assertEqual(result.data['title'], 'An FTIR study of ö and &')
        self.assertEqual(result.data['authors_text'], 'Иван Иванов; Research and Development Team')
        self.assertEqual(result.data['venue'], 'Журнал')
        self.assertEqual(result.data['pages'], '1–12')

    def test_unknown_type_and_fields(self):
        for text in ('@strange{k,title={Title},year={2025},author={Author},custom={value}}',
                     'TY  - XYZ\nTI  - Title\nPY  - 2025\nAU  - Author\nZZ  - value\nER  -'):
            result = parse_publication(text)
            self.assertEqual(result.data['kind'], 'other')
            self.assertEqual(len(result.warnings), 2)
            self.assertTrue(result.unmapped_fields)
            self.assertNotIn('note', result.data)

    def test_incomplete_record_can_be_corrected_in_form(self):
        result = parse_publication('@article{k,title={Title}}')
        self.assertEqual(set(result.errors), {'authors_text'})
        self.assertIsNone(result.data['year'])

    def test_reject_invalid_and_multiple_records(self):
        valid_bib = '@article{k,title={Title}}'
        valid_ris = 'TY  - JOUR\nTI  - Title\nER  -\n'
        for text in ('', 'garbage', '@article{k,title={broken}',
                     valid_bib + '\n@article{broken', valid_bib * 2,
                     valid_ris * 2, valid_ris + 'TY  - JOUR\nTI  - unfinished',
                     'TY  - JOUR\nTI  - missing end', valid_ris + 'garbage'):
            with self.subTest(text=text), self.assertRaises(PublicationImportError):
                parse_publication(text)

    def test_ris_dates_pages_and_continuations(self):
        result = parse_publication('TY  - CHAP\nTI  - Title\nAU  - Smith, Jane\n'
                                   'DA  - 2024/01/01\nT2  - Book\nSP  - 10\nEP  - 20\n'
                                   'AB  - First line\nsecond line\nER  -')
        self.assertEqual(result.errors, {})
        self.assertEqual(result.data['kind'], 'chapter')
        self.assertEqual(result.data['abstract'], 'First line second line')
        self.assertEqual(result.data['pages'], '10–20')

    def test_encoding_and_size(self):
        for source in (b'\xff', b'x' * (2 * 1024 * 1024 + 1)):
            with self.assertRaises(PublicationImportError):
                parse_publication(source)
        self.assertEqual(parse_publication(b'\xef\xbb\xbf@article{k,title={Title}}').data['title'], 'Title')


class DuplicateTests(TestCase):
    def test_normalized_doi_matches_unpublished_without_writes(self):
        publication = Publication.objects.create(title='Existing', year=2026, authors_text='A',
                                                 doi='https://doi.org/10.1234/ABC')
        result = parse_publication('@article{k,title={New},year=2026,author={A},doi={doi:10.1234/abc}}')
        matches = find_duplicates(result)
        self.assertEqual([(m.publication.pk, m.reason) for m in matches], [(publication.pk, 'doi')])
        self.assertEqual(find_duplicates(result, exclude_pk=publication.pk), [])
        self.assertEqual(Publication.objects.count(), 1)

    def test_title_year_fallback(self):
        publication = Publication.objects.create(title='A study: FTIR', year=2026, authors_text='A')
        result = parse_publication('@article{k,title={A STUDY — FTIR},year=2026,author={A}}')
        self.assertEqual(find_duplicates(result)[0].publication.pk, publication.pk)
        result.data['year'] = 2025
        self.assertEqual(find_duplicates(result), [])

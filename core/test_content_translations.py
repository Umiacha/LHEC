from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from core.models import Announcement
from publications.forms import PublicationSearchForm
from publications.models import Publication
from research.models import ResearchDirection
from users.models import Employee


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ContentTranslationTests(TestCase):
    def setUp(self):
        self.addCleanup(translation.deactivate)

    @classmethod
    def setUpTestData(cls):
        cls.employee = Employee.objects.create(
            first_name='Иван', last_name='Иванов', mid_name='Иванович', bio='Русская биография',
            first_name_en='Ivan', last_name_en='Ivanov', mid_name_en='I.', bio_en='English biography',
        )
        cls.direction = ResearchDirection.objects.create(
            name='Русское направление', name_en='English research area', slug='example',
            description='Русское описание', description_en='English description',
            leader=cls.employee, is_published=True,
        )
        cls.announcement = Announcement.objects.create(
            title='Русское объявление', title_en='English announcement',
            text='Русский текст', text_en='English announcement text', is_published=True,
        )

    def test_language_changes_on_same_instances_without_changing_source_fields(self):
        for language, expected in [
            ('en', ('English research area', 'English description', 'Ivanov Ivan I.',
                    'English biography', 'English announcement', 'English announcement text')),
            ('ru', ('Русское направление', 'Русское описание', 'Иванов Иван Иванович',
                    'Русская биография', 'Русское объявление', 'Русский текст')),
            ('en', ('English research area', 'English description', 'Ivanov Ivan I.',
                    'English biography', 'English announcement', 'English announcement text')),
        ]:
            with self.subTest(language=language), translation.override(language):
                self.assertEqual((
                    self.direction.localized_name, self.direction.localized_description,
                    self.employee.localized_full_name, self.employee.localized_bio,
                    self.announcement.localized_title, self.announcement.localized_text,
                ), expected)
        self.assertEqual(self.direction.name, 'Русское направление')
        self.assertEqual(self.employee.last_name, 'Иванов')
        self.assertEqual(self.announcement.text, 'Русский текст')

    def test_empty_or_whitespace_translation_falls_back_per_field(self):
        employee = Employee(first_name='Анна', last_name='Петрова', bio='Биография',
                            first_name_en='Anna', last_name_en='  ', bio_en='\n')
        with translation.override('en'):
            self.assertEqual(employee.localized_full_name, 'Петрова Anna')
            self.assertEqual(employee.localized_bio, 'Биография')
            self.assertEqual(ResearchDirection(name='Направление').localized_name, 'Направление')
            self.assertEqual(Announcement(title='Заголовок').localized_title, 'Заголовок')
            self.assertEqual(Announcement(text='Текст', text_en=' ').localized_text, 'Текст')

    def test_homepage_and_direction_page_use_translated_content(self):
        response = self.client.get('/en/')
        for text in ('English research area', 'English description', 'English announcement',
                     'English announcement text'):
            self.assertContains(response, text)
        self.assertNotContains(response, 'Русское объявление')
        response = self.client.get('/en/science/')
        self.assertContains(response, 'English research area')
        with translation.override('en'):
            url = reverse('research:direction_detail', args=[self.direction.slug])
        response = self.client.get(url)
        for text in ('English research area', 'English description', 'Ivanov Ivan I.'):
            self.assertContains(response, text)
        self.assertNotContains(response, 'Русское описание')
        response = self.client.get('/')
        self.assertContains(response, 'Русское объявление')
        self.assertNotContains(response, 'English announcement')

    def test_employee_profile_and_list_use_translated_content(self):
        with translation.override('en'):
            url = reverse('users:employe_card', args=[self.employee.pk])
            list_url = reverse('users:people')
        response = self.client.get(url)
        for text in ('Ivanov Ivan I.', 'English biography', 'English research area'):
            self.assertContains(response, text)
        self.assertContains(self.client.get(list_url), 'Ivanov Ivan I.')

    def test_english_only_optional_descriptions_are_visible(self):
        self.employee.bio = ''
        self.employee.save()
        self.direction.description = ''
        self.direction.save()
        with translation.override('en'):
            profile = reverse('users:employe_card', args=[self.employee.pk])
            direction = reverse('research:direction_detail', args=[self.direction.slug])
        self.assertContains(self.client.get(profile), 'English biography')
        self.assertContains(self.client.get(direction), 'English description')
        self.assertContains(self.client.get('/en/'), 'English description')

    def test_search_dropdowns_use_translations_with_original_primary_keys(self):
        publication = Publication.objects.create(
            title='Original publication', authors_text='Original authors', year=2026,
            is_published=True,
        )
        publication.employees.add(self.employee)
        publication.research_directions.add(self.direction)
        with translation.override('en'):
            html = PublicationSearchForm().as_p()
        self.assertIn(f'value="{self.employee.pk}">Ivanov Ivan I.', html)
        self.assertIn(f'value="{self.direction.pk}">English research area', html)

    def test_admin_forms_save_translations_alongside_russian_content(self):
        request = RequestFactory().get('/admin/')
        request.user = get_user_model().objects.create_superuser('translator', password='test')
        cases = [
            (self.employee, {'first_name_en': 'John', 'last_name_en': 'Smith',
                             'mid_name_en': '', 'bio_en': 'Updated biography'}),
            (self.direction, {'name_en': 'Updated research area', 'description_en': 'Updated description'}),
            (self.announcement, {'title_en': 'Updated announcement', 'text_en': 'Updated text'}),
        ]
        for obj, changes in cases:
            with self.subTest(model=type(obj).__name__):
                form_class = admin.site._registry[type(obj)].get_form(request, obj)
                initial = form_class(instance=obj).initial
                data = {**initial, **changes}
                if isinstance(obj, Announcement):
                    date = obj.published_at
                    data.update(published_at_0=date.strftime('%Y-%m-%d'),
                                published_at_1=date.strftime('%H:%M:%S'))
                form = form_class(data=data, instance=obj)
                self.assertTrue(form.is_valid(), form.errors)
                form.save()
                obj.refresh_from_db()
                for field, value in changes.items():
                    self.assertEqual(getattr(obj, field), value)
        self.assertEqual(self.employee.first_name, 'Иван')
        self.assertEqual(self.direction.name, 'Русское направление')
        self.assertEqual(self.announcement.title, 'Русское объявление')

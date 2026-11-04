from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import get_template
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from core.gallery import validate_gallery_image
from core.models import Announcement, GalleryPhoto
from education.models import (
    LabWork,
    Lecture,
    LectureCourse,
    LectureFile,
    TeachingMaterial,
)
from publications.forms import PublicationSearchForm
from publications.models import Publication
from research.models import (
    Diploma,
    Dissertation,
    ProjectParticipation,
    ResearchDirection,
    ResearchProject,
)
from users.models import (
    AcademicDegree,
    AcademicTitle,
    EducationStatus,
    Employee,
    EngineerPosition,
    SciencePosition,
)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class HomepagePublicationTests(TestCase):
    def test_selection_order_and_optional_content(self):
        def publication(title, **fields):
            return Publication.objects.create(
                title=title, authors_text='Авторы', year=2025, **fields,
            )

        second = publication('Вторая работа', is_published=True, is_on_homepage=True,
                             homepage_order=2, note='Значимый результат', doi='10.1234/example')
        first = publication('Первая работа', is_published=True, is_on_homepage=True,
                            homepage_order=1)
        publication('Скрытая работа', is_on_homepage=True)
        publication('Только избранная', is_published=True, is_featured=True)
        response = self.client.get(reverse('core:home'))
        self.assertEqual(list(response.context['homepage_publications']), [first, second])
        self.assertContains(response, reverse('publications:publication', args=[first.pk]))
        self.assertContains(response, 'Значимый результат')
        self.assertContains(response, 'https://doi.org/10.1234/example')
        self.assertNotContains(response, 'Скрытая работа')
        self.assertNotContains(response, 'Только избранная')
        content = response.content.decode()
        self.assertLess(content.index('id="science"'), content.index('id="publications"'))
        self.assertLess(content.index('id="publications"'), content.index('id="students"'))

    def test_empty_selection_hides_section(self):
        response = self.client.get(reverse('core:home'))
        self.assertNotContains(response, 'id="publications"')


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class HistoryStatisticsTests(TestCase):
    def test_counts_current_staff_and_degrees_among_scientists(self):
        def employee(**fields):
            return Employee.objects.create(last_name='Тест', first_name='Сотрудник', **fields)

        employee(science_position=SciencePosition.RESEARCH_FELLOW,
                 academic_degree=AcademicDegree.CANDIDATE_CHEMISTRY)
        employee(science_position=SciencePosition.SENIOR_RESEARCH_FELLOW,
                 academic_degree=AcademicDegree.CANDIDATE_PHYS_MATH, is_published=False)
        employee(science_position=SciencePosition.HEAD_OF_THE_LABORATORY,
                 engineer_position=EngineerPosition.TECHNICIAN,
                 academic_degree=AcademicDegree.DOCTOR_CHEMISTRY)
        employee(science_position=SciencePosition.JUNIOR_RESEARCH_FELLOW)
        employee(engineer_position=EngineerPosition.TECHNICIAN,
                 academic_degree=AcademicDegree.DOCTOR_PHYS_MATH)
        employee(is_current=False, science_position=SciencePosition.RESEARCH_FELLOW,
                 academic_degree=AcademicDegree.CANDIDATE_BIOLOGY)

        response = self.client.get(reverse('core:history'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['staff_statistics'], {
            'total': 5, 'scientific': 4, 'doctors': 1, 'candidates': 2,
        })
        self.assertContains(response, 'Сегодня коллектив лаборатории — 5 сотрудников, в том числе — 4 научных сотрудников, среди которых 1 доктора и 2 кандидатов наук.')

    def test_empty_staff_renders_zero_counts(self):
        response = self.client.get(reverse('core:history'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['staff_statistics'], {
            'total': 0, 'scientific': 0, 'doctors': 0, 'candidates': 0,
        })
        self.assertContains(response, 'Сегодня коллектив лаборатории — 0 сотрудников, в том числе — 0 научных сотрудников.')
        self.assertNotContains(response, 'среди которых')

    def test_hides_degree_group_with_zero_members(self):
        employee = Employee.objects.create(
            last_name='Тест', first_name='Сотрудник',
            science_position=SciencePosition.RESEARCH_FELLOW,
            academic_degree=AcademicDegree.DOCTOR_CHEMISTRY,
        )
        response = self.client.get(reverse('core:history'))
        self.assertContains(response, 'среди которых 1 доктора наук.')
        self.assertNotContains(response, 'кандидатов наук')

        employee.academic_degree = AcademicDegree.CANDIDATE_CHEMISTRY
        employee.save(update_fields=['academic_degree'])
        response = self.client.get(reverse('core:history'))
        self.assertContains(response, 'среди которых 1 кандидатов наук.')
        self.assertNotContains(response, 'доктора наук')


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


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ExtendedTranslationTests(TestCase):
    def setUp(self):
        self.addCleanup(translation.deactivate)

    def test_history_prose_and_all_statistics_branches_are_translated(self):
        request = RequestFactory().get('/en/about/history/')
        request.user = AnonymousUser()
        with translation.override('en'):
            for doctors, candidates in ((0, 0), (1, 0), (0, 1), (2, 3)):
                with self.subTest(doctors=doctors, candidates=candidates):
                    html = get_template('core/history.html').render({'staff_statistics': {
                        'total': 7, 'scientific': 5, 'doctors': doctors, 'candidates': candidates,
                    }}, request=request)
                    self.assertIn('The world’s first course in radiation chemistry', html)
                    self.assertIn('Vladimir I. Feldman', html)
                    self.assertIn('7 staff members, including 5 researchers', html)
                    # The linked article retains its original official title.
                    self.assertNotRegex(html.replace('История радиационной химии', ''), '[А-Яа-яЁё]')

    def test_project_and_external_participant_render_in_english(self):
        project = ResearchProject.objects.create(
            name='Русский проект', name_en='English project', slug='translated',
            start_year=2025, end_year=2030, is_published=True,
            abstract_en='English-only abstract', funding_source_en='English funder',
            customer_en='English customer', funding_program_en='English programme',
            funding_kind=ResearchProject.FundingKind.GRANT,
        )
        ProjectParticipation.objects.create(project=project, external_name='Русское имя',
            external_name_en='External Researcher', external_organization='Организация',
            external_organization_en='External Organization')
        with translation.override('en'):
            response = self.client.get(reverse('research:project_detail', args=[project.slug]))
        for text in ('English project', 'English-only abstract', 'English funder',
                     'English customer', 'English programme', 'External Researcher',
                     'External Organization', 'Grant'):
            self.assertContains(response, text)
        self.assertNotContains(response, 'Русское имя')
        self.assertContains(self.client.get('/en/science/'), 'English project')
        with translation.override('en'):
            self.assertContains(self.client.get(reverse('research:projects')), 'Current')
        with translation.override('ru'):
            self.assertEqual(project.localized_name, 'Русский проект')

    def test_publication_preserves_metadata_and_searches_english_authors(self):
        publication = Publication.objects.create(
            title='Оригинальное название статьи', authors_text='Оригинальные авторы',
            authors_text_en='Manual English Authors', note_en='English-only laboratory note',
            venue='Оригинальный журнал', year=2026, is_published=True, is_on_homepage=True,
        )
        with translation.override('en'):
            url = reverse('publications:publication', args=[publication.pk])
            search = reverse('publications:publications')
        response = self.client.get(url)
        for text in ('Оригинальное название статьи', 'Оригинальный журнал',
                     'Manual English Authors', 'English-only laboratory note', 'Article'):
            self.assertContains(response, text)
        self.assertContains(self.client.get('/en/'), 'English-only laboratory note')
        self.assertContains(self.client.get(search, {'q': 'Manual English'}), publication.title)
        self.assertNotContains(response, 'Оригинальные авторы')
        publication.authors_text_en = ' '
        with translation.override('en'):
            self.assertEqual(publication.localized_authors_text, 'Оригинальные авторы')

    def test_gallery_caption_is_used_for_text_alt_and_link_label(self):
        GalleryPhoto.objects.bulk_create([GalleryPhoto(
            caption='Русская подпись', caption_en='English photo caption', year=2026,
            image='gallery/original.jpg', thumbnail='gallery/thumbnail.jpg', is_published=True,
        )])
        response = self.client.get('/en/gallery/')
        self.assertContains(response, 'English photo caption', count=3)
        self.assertContains(response, 'Open photo: English photo caption (in a new tab)')
        self.assertNotContains(response, 'Русская подпись')

    def test_fixed_position_degree_and_education_labels_follow_language(self):
        employee = Employee(science_position=SciencePosition.SENIOR_RESEARCH_FELLOW,
            engineer_position=EngineerPosition.LEADING_ENGINEER,
            education_status=EducationStatus.STUDENT, study_year=3,
            academic_degree=AcademicDegree.CANDIDATE_CHEMISTRY,
            academic_title=AcademicTitle.DOCENT)
        with translation.override('en'):
            self.assertEqual(employee.get_science_position_display(), 'Senior Researcher')
            self.assertEqual(employee.get_engineer_position_display(), 'Leading Engineer')
            self.assertEqual(employee.education_label, 'Student, year 3')
            self.assertEqual(employee.get_academic_degree_display(), 'PhD in Chemistry')
            self.assertEqual(employee.get_academic_title_display(), 'Associate Professor')
        with translation.override('ru'):
            self.assertEqual(employee.education_label, 'Студент, 3 курс')
            self.assertEqual(employee.get_science_position_display(), 'с.н.с.')
        self.assertEqual(employee.science_position, 'senior_research_fellow')

    def test_teaching_descriptions_translate_but_document_titles_stay_original(self):
        lab = LabWork.objects.create(title='Официальное название работы', slug='lab',
            short_description='Описание', short_description_en='English summary',
            description_en='English-only lab description', equipment_en='English equipment')
        TeachingMaterial.objects.create(title='Название документа', description_en='English material',
            file='education/materials/example.pdf', lab_work=lab)
        response = self.client.get('/en/students/study_materials/')
        for text in ('Официальное название работы', 'Название документа', 'English summary',
                     'English-only lab description', 'English equipment', 'English material'):
            self.assertContains(response, text)
        course = LectureCourse.objects.create(title='Название курса', slug='course',
            description_en='English course description', is_published=True)
        lecture = Lecture.objects.create(course=course, title='Название лекции',
            note_en='English lecturer note', is_published=True)
        LectureFile.objects.create(lecture=lecture, title='Подпись', title_en='English file label',
            file='education/lectures/example.pdf')
        user = User.objects.create_superuser('reader', password='test')
        self.client.force_login(user)
        with translation.override('en'):
            response = self.client.get(reverse('education:lecture_course_detail', args=[course.slug]))
        for text in ('Название курса', 'Название лекции', 'English course description',
                     'English lecturer note', 'English file label'):
            self.assertContains(response, text)

    def test_added_translations_are_editable_in_registered_admin_forms(self):
        request = RequestFactory().get('/admin/')
        request.user = User(is_superuser=True, is_staff=True)
        for model in (ResearchProject, Dissertation, Diploma, GalleryPhoto, Publication,
                      LabWork, TeachingMaterial, LectureCourse, Lecture):
            with self.subTest(model=model.__name__):
                form = admin.site._registry[model].get_form(request)
                fields = [field.name for field in model._meta.fields if field.name.endswith('_en')]
                self.assertTrue(fields)
                for field in fields:
                    self.assertIn(field, form.base_fields)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class GalleryTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = override_settings(MEDIA_ROOT=directory.name)
        settings.enable()
        self.addCleanup(settings.disable)

    def upload(self, name='photo.png', size=(1200, 800)):
        output = BytesIO()
        Image.new('RGB', size, 'red').save(output, 'PNG')
        return SimpleUploadedFile(name, output.getvalue(), content_type='image/png')

    def photo(self, **kwargs):
        return GalleryPhoto.objects.create(
            image=self.upload(), year=1985, caption='Архивный снимок', **kwargs,
        )

    def test_archive_path_and_thumbnail(self):
        photo = self.photo()
        self.assertTrue(photo.image.name.startswith('gallery/1985/'))
        self.assertTrue(photo.thumbnail.name.startswith('gallery/1985/thumbnails/'))
        with Image.open(photo.thumbnail.path) as preview:
            self.assertEqual(preview.size, (960, 640))
            self.assertEqual(preview.format, 'JPEG')
        original = photo.image.name
        thumbnail = photo.thumbnail.name
        photo.year = 1986
        photo.save()
        self.assertEqual(photo.image.name, original)
        self.assertEqual(photo.thumbnail.name, thumbnail)

    def test_replacement_and_bulk_deletion_clean_files(self):
        photo = self.photo()
        old_paths = [photo.image.path, photo.thumbnail.path]
        photo.image = self.upload()
        photo.year = 1990
        with self.captureOnCommitCallbacks(execute=True):
            photo.save()
        self.assertTrue(photo.image.name.startswith('gallery/1990/'))
        self.assertTrue(all(not Path(path).exists() for path in old_paths))
        paths = [photo.image.path, photo.thumbnail.path]
        with self.captureOnCommitCallbacks(execute=True):
            GalleryPhoto.objects.all().delete()
        self.assertTrue(all(not Path(path).exists() for path in paths))

    def test_public_page_hides_drafts_and_escapes_caption(self):
        hidden = self.photo()
        public = self.photo(is_published=True)
        public.caption = '<script>alert(1)</script>'
        public.save()
        response = self.client.get(reverse('core:gallery'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['page_obj']), [public])
        self.assertContains(response, public.thumbnail.url)
        self.assertContains(response, public.image.url)
        self.assertNotContains(response, hidden.image.url)
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>')

    def test_pagination_and_empty_state(self):
        response = self.client.get(reverse('core:gallery'))
        self.assertContains(response, 'Фотографии скоро появятся.')
        photo = self.photo(is_published=True)
        # Reuse the files to exercise pagination without generating 24 more images.
        GalleryPhoto.objects.bulk_create([
            GalleryPhoto(image=photo.image.name, thumbnail=photo.thumbnail.name,
                         caption=f'Фото {i}', year=1985, is_published=True)
            for i in range(24)
        ])
        response = self.client.get(reverse('core:gallery'), {'page': 2})
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertContains(response, 'Страница 2 из 2')

    def test_rejects_invalid_and_oversized_uploads(self):
        with self.assertRaises(ValidationError):
            validate_gallery_image(SimpleUploadedFile('bad.jpg', b'not an image'))
        oversized = self.upload()
        oversized.size = 21 * 1024 * 1024
        with self.assertRaises(ValidationError):
            validate_gallery_image(oversized)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class LanguageTests(TestCase):
    def test_russian_default_even_with_english_browser_or_cookie(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'en'
        response = self.client.get('/', HTTP_ACCEPT_LANGUAGE='en')
        self.assertContains(response, '<html lang="ru">')
        self.assertContains(response, 'Лаборатория химии высоких энергий')
        self.assertEqual(response.headers['Content-Language'], 'ru')

    def test_english_interface_and_untranslated_database_content(self):
        Announcement.objects.create(title='Объявление из базы', text='Исходный текст', is_published=True)
        response = self.client.get('/en/')
        self.assertContains(response, '<html lang="en">')
        self.assertContains(response, 'Laboratory of High Energy Chemistry')
        self.assertContains(response, 'For students')
        self.assertContains(response, 'Объявление из базы')
        self.assertContains(response, 'href="/en/science/"')
        self.assertEqual(response.headers['Content-Language'], 'en')

    def test_language_switch_preserves_page_and_query_in_both_directions(self):
        response = self.client.post('/i18n/setlang/', {
            'language': 'en', 'next': '/gallery/?page=2',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/en/gallery/?page=2')
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'en')
        response = self.client.post('/en/i18n/setlang/', {
            'language': 'ru', 'next': '/en/gallery/?page=2',
        })
        self.assertEqual(response.url, '/gallery/?page=2')

    def test_switch_rejects_external_redirect_and_requires_csrf(self):
        response = self.client.post('/i18n/setlang/', {
            'language': 'en', 'next': 'https://example.com/',
        })
        self.assertEqual(response.url, '/en/')
        self.assertEqual(Client(enforce_csrf_checks=True).post(
            '/i18n/setlang/', {'language': 'en'},
        ).status_code, 403)

    def test_public_pages_and_login_render_in_english(self):
        names = ['core:home', 'research:science', 'core:gallery', 'core:contacts',
                 'core:history', 'core:news', 'users:people', 'users:login',
                 'education:students', 'publications:publications', 'research:projects']
        with translation.override('en'):
            for name in names:
                with self.subTest(page=name):
                    response = self.client.get(reverse(name))
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, '<html lang="en">')
            response = self.client.get(reverse('users:login'))
        self.assertContains(response, 'Username')
        self.assertContains(response, 'Password')
        self.assertContains(response, 'Staff sign-in')

    def test_shared_pagination_is_translated(self):
        from django.core.paginator import Paginator
        page = Paginator(range(3), 1).page(2)
        from django.contrib.auth.models import AnonymousUser
        request = RequestFactory().get('/en/gallery/')
        request.user = AnonymousUser()
        with translation.override('en'):
            html = get_template('core/components/pagination.html').render(
                {'page_obj': page}, request=request,
            )
        self.assertIn('Page 2 of 3', html)
        self.assertIn('Next', html)

    def test_all_public_templates_compile(self):
        for app in ('core', 'users', 'education', 'research', 'publications'):
            for path in (settings.BASE_DIR / app / 'templates' / app).rglob('*.html'):
                with self.subTest(template=str(path)):
                    get_template(str(path.relative_to(settings.BASE_DIR / app / 'templates')))


class NewsPageTests(TestCase):
    def test_only_published_due_announcements_are_visible(self):
        from datetime import timedelta
        from django.utils import timezone

        now = timezone.now()
        older = Announcement.objects.create(
            title='Older announcement', text='Older text', is_published=True,
            published_at=now - timedelta(days=2),
        )
        newer = Announcement.objects.create(
            title='Newer announcement', text='<script>alert(1)</script>\nSecond line',
            is_published=True, published_at=now - timedelta(days=1),
        )
        Announcement.objects.create(title='Hidden draft', text='Draft text')
        Announcement.objects.create(
            title='Future announcement', text='Future text', is_published=True,
            published_at=now + timedelta(days=1),
        )
        response = self.client.get(reverse('core:news'))
        self.assertTemplateUsed(response, 'core/news.html')
        self.assertTemplateNotUsed(response, 'core/_placeholder.html')
        self.assertEqual(list(response.context['page_obj']), [newer, older])
        self.assertNotContains(response, 'Hidden draft')
        self.assertNotContains(response, 'Future announcement')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;<br>Second line')
        self.assertNotContains(response, 'in_development.JPG')

    def test_pagination_and_translation(self):
        from datetime import timedelta
        from django.utils import timezone

        for index in range(11):
            Announcement.objects.create(
                title=f'Объявление {index}', text='Текст',
                title_en=f'Announcement {index}', text_en='English text',
                is_published=True, published_at=timezone.now() - timedelta(days=index),
            )
        response = self.client.get('/en/news/')
        self.assertEqual(len(response.context['page_obj']), 10)
        self.assertContains(response, 'Announcement 0')
        self.assertContains(response, 'English text')
        self.assertContains(response, 'href="?page=2"')
        response = self.client.get('/en/news/?page=2')
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertContains(response, 'Announcement 10')
        self.assertNotContains(response, 'Announcement 0')

    def test_empty_page(self):
        response = self.client.get(reverse('core:news'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Сейчас новых объявлений нет.')
        self.assertNotContains(response, 'in_development.JPG')

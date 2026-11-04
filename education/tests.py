from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import importlib
import tempfile

from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from education.admin import LectureInline
from education.models import (
    LabWork,
    Lecture,
    LectureCourse,
    LectureFile,
    StudentWorkTopic,
    TeachingMaterial,
)
from research.models import Diploma, Dissertation, ResearchProject
from users.models import Employee


class LectureAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = get_user_model().objects.create_superuser(
            username='lecture-admin', password='test-password',
        )
        cls.course = LectureCourse.objects.create(title='Курс', slug='course')
        cls.lecture = Lecture.objects.create(course=cls.course, title='Лекция')
        LectureFile.objects.create(
            lecture=cls.lecture, file='education/lectures/slides.pdf',
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_course_contains_link_to_edit_lecture(self):
        response = self.client.get(reverse(
            'admin:education_lecturecourse_change', args=[self.course.pk],
        ))
        self.assertContains(response, reverse(
            'admin:education_lecture_change', args=[self.lecture.pk],
        ))

    def test_lecture_with_private_attachment_renders_without_public_url(self):
        response = self.client.get(reverse(
            'admin:education_lecture_change', args=[self.lecture.pk],
        ))
        self.assertContains(response, 'slides.pdf')
        self.assertContains(response, reverse(
            'education:download_lecture_file',
            kwargs={'file_name': 'education/lectures/slides.pdf'},
        ))
        self.assertContains(response, 'name="files-0-file"')
        self.assertContains(response, 'name="files-0-DELETE"')


class LectureDownloadTests(TestCase):
    def setUp(self):
        private_root = TemporaryDirectory()
        self.addCleanup(private_root.cleanup)
        settings = override_settings(PRIVATE_PUBLICATIONS_ROOT=private_root.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.course = LectureCourse.objects.create(
            title='Курс', slug='course', is_published=True,
        )
        self.lecture = Lecture.objects.create(
            course=self.course, title='Лекция', is_published=True,
        )
        self.attachment = LectureFile.objects.create(
            lecture=self.lecture,
            file=SimpleUploadedFile('slides.pdf', b'lecture contents'),
        )
        self.url = self.attachment.file.url
        self.user = get_user_model().objects.create_user(username='employee')

    def login_employee(self):
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label='education', codename='view_internal_materials',
        ))
        self.client.force_login(self.user)

    def test_anonymous_and_user_without_permission_are_denied(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_employee_can_download(self):
        self.login_employee()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'lecture contents')
        self.assertIn('attachment;', response['Content-Disposition'])

    def test_superuser_can_download(self):
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b''.join(response.streaming_content))

    def test_unpublished_lecture_or_course_is_not_available(self):
        self.login_employee()
        self.lecture.is_published = False
        self.lecture.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.lecture.is_published = True
        self.lecture.save()
        self.course.is_published = False
        self.course.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_missing_file_returns_404(self):
        self.login_employee()
        self.attachment.file.storage.delete(self.attachment.file.name)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_pdf_preview_requires_permission_and_is_not_cached(self):
        url = reverse('education:view_lecture_file', args=[self.attachment.file.name])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.login_employee()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('inline;', response['Content-Disposition'])
        self.assertIn('no-store', response['Cache-Control'])
        self.assertTrue(b''.join(response.streaming_content))
        self.course.is_published = False
        self.course.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_non_pdf_preview_downloads_instead(self):
        self.login_employee()
        self.attachment.file.name = 'education/lectures/demo.html'
        self.attachment.file.save('demo.html', SimpleUploadedFile('demo.html', b'<html>demo</html>'))
        response = self.client.get(reverse(
            'education:view_lecture_file', args=[self.attachment.file.name],
        ))
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertTrue(b''.join(response.streaming_content))


class LectureModelsTests(TestCase):
    def test_attachment_is_stored_privately_without_public_url(self):
        with TemporaryDirectory() as private_root, TemporaryDirectory() as media_root:
            with override_settings(
                PRIVATE_PUBLICATIONS_ROOT=private_root, MEDIA_ROOT=media_root,
            ):
                course = LectureCourse.objects.create(title='Курс', slug='course')
                lecture = Lecture.objects.create(course=course, title='Лекция')
                attachment = LectureFile.objects.create(
                    lecture=lecture,
                    file=SimpleUploadedFile('slides.pdf', b'lecture contents'),
                )
                self.assertTrue(Path(attachment.file.path).is_relative_to(private_root))
                self.assertEqual(attachment.file.read(), b'lecture contents')
                attachment.file.close()
                self.assertEqual(list(Path(media_root).iterdir()), [])
                self.assertEqual(attachment.file.url, reverse(
                    'education:download_lecture_file',
                    kwargs={'file_name': attachment.file.name},
                ))

    def test_deleting_course_removes_lectures_and_attachment_records(self):
        course = LectureCourse.objects.create(title='Курс', slug='course')
        lecture = Lecture.objects.create(course=course, title='Лекция')
        LectureFile.objects.create(lecture=lecture, file='education/lectures/slides.pdf')

        course.delete()

        self.assertFalse(Lecture.objects.exists())
        self.assertFalse(LectureFile.objects.exists())


class LecturePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='reader')
        cls.employee = get_user_model().objects.create_user(username='employee-reader')
        cls.employee.user_permissions.add(Permission.objects.get(
            content_type__app_label='education', codename='view_internal_materials',
        ))
        cls.course = LectureCourse.objects.create(
            title='Опубликованный курс', slug='published', is_published=True,
            description='Описание курса',
        )
        cls.draft = LectureCourse.objects.create(title='Скрытый курс', slug='draft')
        cls.lecture = Lecture.objects.create(
            course=cls.course, title='Первая лекция', note='Примечание <script>alert(1)</script>',
            is_published=True, order=2,
        )
        Lecture.objects.create(course=cls.course, title='Ранняя лекция', is_published=True, order=1)
        Lecture.objects.create(course=cls.course, title='Скрытая лекция')
        cls.attachment = LectureFile.objects.create(
            lecture=cls.lecture, title='Презентация', file='education/lectures/slides.pdf',
        )
        cls.course_url = reverse('education:lecture_course_detail', args=[cls.course.slug])
        cls.list_url = reverse('education:study_materials')

    def test_visitors_and_accounts_without_permission_cannot_see_courses(self):
        for user in (None, self.user):
            if user:
                self.client.force_login(user)
            with self.subTest(user=user):
                response = self.client.get(self.list_url)
                self.assertNotContains(response, self.course.title)
                self.assertNotContains(response, 'lecture-courses-title')
                self.assertEqual(self.client.get(self.course_url).status_code, 403)

    def test_employee_sees_only_published_courses(self):
        self.client.force_login(self.employee)
        response = self.client.get(self.list_url)
        self.assertContains(response, self.course_url)
        self.assertNotContains(response, self.draft.title)
        self.assertEqual(self.client.get(reverse(
            'education:lecture_course_detail', args=[self.draft.slug],
        )).status_code, 404)

    def test_course_shows_ordered_lectures_notes_and_protected_file_links(self):
        self.client.force_login(self.employee)
        response = self.client.get(self.course_url)
        self.assertContains(response, '<details id="lecture-', count=2)
        self.assertNotContains(response, 'Скрытая лекция')
        self.assertContains(response, '&lt;script&gt;')
        self.assertContains(response, self.attachment.file.url)
        self.assertContains(response, reverse(
            'education:view_lecture_file', args=[self.attachment.file.name],
        ))
        self.assertLess(response.content.index('Ранняя лекция'.encode()),
                        response.content.index('Первая лекция'.encode()))
        self.assertIn('no-store', response['Cache-Control'])

    def test_empty_course_has_helpful_message(self):
        self.client.force_login(self.employee)
        self.course.lectures.all().delete()
        response = self.client.get(self.course_url)
        self.assertContains(response, 'Лекции этого курса пока не опубликованы.')


class MaterialStorageTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        settings = override_settings(
            MEDIA_ROOT=self.root / 'public',
            PRIVATE_PUBLICATIONS_ROOT=self.root / 'private',
        )
        settings.enable()
        self.addCleanup(settings.disable)

    def material(self, **kwargs):
        return TeachingMaterial.objects.create(
            title='Document', file=SimpleUploadedFile('guide.pdf', b'document'), **kwargs,
        )

    def test_storage_and_download_permissions(self):
        material = self.material()
        self.assertTrue(Path(material.file.path).is_relative_to(self.root / 'private'))
        self.assertFalse((self.root / 'public' / material.file.name).exists())
        self.assertEqual(material.file.url, material.get_download_url())
        response = self.client.get(material.get_download_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'document')
        material.access_level = TeachingMaterial.AccessLevel.INTERNAL
        material.save()
        self.assertEqual(self.client.get(material.get_download_url()).status_code, 403)
        user = get_user_model().objects.create_superuser('admin', password='test')
        self.client.force_login(user)
        response = self.client.get(material.get_download_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'document')
        material.is_published = False
        material.save()
        self.assertEqual(self.client.get(material.get_download_url()).status_code, 404)

    def test_missing_file_returns_404(self):
        material = self.material()
        Path(material.file.path).unlink()
        self.assertEqual(self.client.get(material.get_download_url()).status_code, 404)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class TranslatedTitleTests(TestCase):
    def setUp(self):
        self.addCleanup(translation.deactivate)

    def test_optional_titles_follow_language_and_fall_back(self):
        for model in (LabWork, TeachingMaterial, LectureCourse, Lecture,
                      StudentWorkTopic, Dissertation, Diploma):
            with self.subTest(model=model.__name__):
                obj = model(title='Исходное название', title_en='English title')
                with translation.override('en'):
                    self.assertEqual(obj.localized_title, 'English title')
                    obj.title_en = '  '
                    self.assertEqual(obj.localized_title, 'Исходное название')
                obj.title_en = 'English title'
                with translation.override('ru'):
                    self.assertEqual(obj.localized_title, 'Исходное название')

    def test_courses_lectures_and_material_titles_render_in_english(self):
        lab = LabWork.objects.create(title='Лабораторная работа', title_en='English lab',
                                    slug='lab', short_description='Description')
        TeachingMaterial.objects.create(title='Материал', title_en='English material title',
                                        lab_work=lab, file='materials/example.pdf')
        course = LectureCourse.objects.create(title='Курс', title_en='English course title',
                                             slug='translated-course', is_published=True)
        Lecture.objects.create(course=course, title='Лекция', title_en='English lecture title',
                               is_published=True)
        user = User.objects.create_superuser('teacher', password='test')
        self.client.force_login(user)
        response = self.client.get('/en/students/study_materials/')
        for title in ('English lab', 'English material title', 'English course title'):
            self.assertContains(response, title)
        with translation.override('en'):
            response = self.client.get(reverse('education:lecture_course_detail', args=[course.slug]))
        self.assertContains(response, '<h1 class="mt-3 page-title">English course title</h1>', html=True)
        self.assertContains(response, 'English lecture title')
        self.assertNotContains(response, 'Лекция')
        with translation.override('ru'):
            response = self.client.get(reverse('education:lecture_course_detail', args=[course.slug]))
        self.assertContains(response, 'Лекция')
        self.assertNotContains(response, 'English lecture title')

    def test_science_page_renders_optional_dissertation_and_diploma_titles(self):
        author = Employee.objects.create(last_name='Иванов', first_name='Иван')
        Dissertation.objects.create(title='Диссертация', title_en='English dissertation title',
            author='Автор', external_url='https://example.com/dissertation', year=2026, is_published=True)
        Diploma.objects.create(title='Диплом', title_en='English diploma title', author=author,
            external_url='https://example.com/diploma', year=2026, level=Diploma.Level.MASTER, is_published=True)
        response = self.client.get('/en/science/')
        self.assertContains(response, 'English dissertation title')
        self.assertContains(response, 'English diploma title')
        response = self.client.get('/science/')
        self.assertContains(response, 'Диссертация')
        self.assertNotContains(response, 'English dissertation title')

    def test_archive_uses_editor_entered_translation_and_hides_unpublished_topics(self):
        topic = StudentWorkTopic.objects.create(title='Русская тема', title_en='English course topic',
            kind=StudentWorkTopic.Kind.COURSE, subject=StudentWorkTopic.Subject.PHYSICAL)
        StudentWorkTopic.objects.create(title='Скрытая тема', title_en='Hidden topic',
            kind=StudentWorkTopic.Kind.COURSE, is_published=False)
        StudentWorkTopic.objects.create(title='Исходный диплом', title_en='English archived diploma',
            kind=StudentWorkTopic.Kind.DIPLOMA)
        response = self.client.get('/en/students/theses/')
        for title in ('English course topic', 'English archived diploma', 'Physical chemistry'):
            self.assertContains(response, title)
        self.assertNotContains(response, 'Hidden topic')
        self.assertNotContains(response, 'Русская тема')
        topic.title_en = ''
        topic.save()
        self.assertContains(self.client.get('/en/students/theses/'), 'Русская тема')

    def test_migration_preserves_all_existing_topics_and_does_not_overwrite_edits(self):
        self.assertEqual(StudentWorkTopic.objects.filter(kind='diploma').count(), 18)
        self.assertEqual(StudentWorkTopic.objects.filter(kind='course').count(), 22)
        StudentWorkTopic.objects.all().delete()
        migration = importlib.import_module('education.migrations.0002_seed_student_work_topics')
        migration.seed_topics(apps, SimpleNamespace(connection=connection))
        self.assertEqual(StudentWorkTopic.objects.count(), 40)
        self.assertEqual(StudentWorkTopic.objects.filter(kind='diploma').count(), 18)
        self.assertEqual(StudentWorkTopic.objects.filter(kind='course').count(), 22)
        topic = StudentWorkTopic.objects.get(title='Синтез ацетиладамантана')
        topic.title_en = 'Editor-approved title'
        topic.save()
        migration.seed_topics(apps, SimpleNamespace(connection=connection))
        topic.refresh_from_db()
        self.assertEqual(StudentWorkTopic.objects.count(), 40)
        self.assertEqual(topic.title_en, 'Editor-approved title')

    def test_title_fields_are_editable_in_admin_including_lecture_inline(self):
        request = RequestFactory().get('/admin/')
        request.user = User(is_superuser=True, is_staff=True)
        for model in (LabWork, TeachingMaterial, LectureCourse, Lecture,
                      StudentWorkTopic, Dissertation, Diploma):
            with self.subTest(model=model.__name__):
                form_class = admin.site._registry[model].get_form(request)
                self.assertIn('title_en', form_class.base_fields)
                self.assertFalse(form_class.base_fields['title_en'].required)
        form = admin.site._registry[ResearchProject].get_form(request)
        self.assertIn('name_en', form.base_fields)
        self.assertIn('title_en', LectureInline(LectureCourse, admin.site).get_formset(request).form.base_fields)

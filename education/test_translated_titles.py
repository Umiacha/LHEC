import importlib
from types import SimpleNamespace

from django.apps import apps
from django.contrib import admin
from django.contrib.auth.models import User
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from education.admin import LectureInline
from education.models import LabWork, Lecture, LectureCourse, StudentWorkTopic, TeachingMaterial
from research.models import Diploma, Dissertation, ResearchProject
from users.models import Employee


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
        StudentWorkTopic.objects.all().delete()
        migration = importlib.import_module('education.migrations.0008_seed_student_work_topics')
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

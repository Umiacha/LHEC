from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import Lecture, LectureCourse, LectureFile


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

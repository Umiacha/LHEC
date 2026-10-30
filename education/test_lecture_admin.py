from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Lecture, LectureCourse, LectureFile


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

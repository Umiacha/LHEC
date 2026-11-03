from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Lecture, LectureCourse, LectureFile


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

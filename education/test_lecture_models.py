from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Lecture, LectureCourse, LectureFile


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

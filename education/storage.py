"""Приватное хранилище лекций и совместимость с миграцией education.0002."""
from research.storage import DiplomaFileStorage
from django.urls import reverse
from django.utils.deconstruct import deconstructible

from publications.storage import PublicationFileStorage


@deconstructible
class LectureFileStorage(PublicationFileStorage):
    """Вложения лекций в приватном каталоге, без публичных URL."""

    def url(self, name):
        return reverse('education:download_lecture_file', kwargs={'file_name': name})


lecture_file_storage = LectureFileStorage()

from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.urls import reverse
from django.utils.deconstruct import deconstructible


@deconstructible
class PublicationFileStorage(FileSystemStorage):
    """
    Отдельная директория для раздачи файлов.
    
    Нужна, чтобы обойти прямое скачивание по /media/.
    """
    @property
    def base_location(self):
        return settings.PRIVATE_PUBLICATIONS_ROOT

    @property
    def location(self):
        # PRIVATE_PUBLICATIONS_ROOT can change in tests, independently of MEDIA_ROOT.
        # FileSystemStorage only invalidates its cached location for MEDIA_ROOT.
        return str(Path(self.base_location).absolute())

    def url(self, name):
        return reverse('publications:download_file', kwargs={'file_name': name})


publication_file_storage = PublicationFileStorage()

from django.urls import reverse
from django.utils.deconstruct import deconstructible

from publications.storage import PublicationFileStorage


@deconstructible
class DissertationFileStorage(PublicationFileStorage):
    """Тексты диссертаций в существующем закрытом хранилище материалов."""

    def url(self, name):
        return reverse('research:download_dissertation', kwargs={'file_name': name})


dissertation_file_storage = DissertationFileStorage()


@deconstructible
class DiplomaFileStorage(PublicationFileStorage):
    """Тексты ВКР в закрытом хранилище материалов."""

    def url(self, name):
        return reverse('research:download_diploma', kwargs={'file_name': name})


diploma_file_storage = DiplomaFileStorage()

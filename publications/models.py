from django.utils.translation import gettext_lazy as _
from pathlib import Path

from django.db import models

from core.i18n import localized_value

from .storage import publication_file_storage


class Publication(models.Model):
    """Научная публикация."""
    class Kind(models.TextChoices):
        ARTICLE = 'article', _('Статья')
        CONFERENCE = 'conference', _('Материалы конференции')
        BOOK = 'book', _('Книга')
        CHAPTER = 'chapter', _('Глава в книге')
        OTHER = 'other', _('Другое')

    title = models.CharField(verbose_name='Название', max_length=500)
    year = models.PositiveSmallIntegerField(verbose_name='Год', null=True, blank=True)
    authors_text = models.TextField(verbose_name='Авторы')
    employees = models.ManyToManyField(
        'users.Employee',
        blank=True,
        related_name='publications',
        verbose_name='Сотрудники лаборатории среди авторов'
    )
    research_directions = models.ManyToManyField(
        'research.ResearchDirection',
        blank=True,
        related_name='publications',
        verbose_name='Научные направления',
    )
    kind = models.CharField(
        'Тип',
        max_length=20,
        choices=Kind.choices,
        default=Kind.ARTICLE,
    )
    venue = models.CharField(
        'Журнал, сборник или конференция',
        max_length=500,
        blank=True,
    )
    volume = models.CharField('Том', max_length=50, blank=True)
    issue = models.CharField('Номер', max_length=50, blank=True)
    pages = models.CharField('Страницы или номер статьи', max_length=50, blank=True)

    doi = models.CharField('DOI', max_length=255, blank=True)
    istina_url = models.URLField('Ссылка на Истину', blank=True)
    external_url = models.URLField('Другая ссылка', blank=True)

    abstract = models.TextField('Аннотация', blank=True)
    note = models.TextField('Примечание лаборатории', blank=True)

    is_published = models.BooleanField('Показывать на сайте', default=False)
    is_featured = models.BooleanField('Избранная', default=False)
    is_on_homepage = models.BooleanField('На главной', default=False)
    homepage_order = models.PositiveIntegerField(
        'Порядок на главной', default=0, blank=True,
        help_text='Меньшие значения показываются первыми. При совпадении — сначала новые работы.',
    )
    created_at = models.DateTimeField('Запись создана', auto_now_add=True)
    updated_at = models.DateTimeField('Запись изменена', auto_now=True)

    note_en = models.TextField('Примечание лаборатории — EN', blank=True)
    authors_text_en = models.TextField('Авторы — EN', blank=True)

    @property
    def localized_note(self):
        return localized_value(self, "note")

    @property
    def localized_authors_text(self):
        return localized_value(self, "authors_text")

    class Meta:
        verbose_name = 'Публикация'
        verbose_name_plural = 'Публикации'
        ordering = (models.F('year').desc(nulls_last=True), '-id')

    def __str__(self):
        return f'{self.authors_text}: {self.title}' + (f' ({self.year})' if self.year else '')


def publication_file_path(instance, filename):
    """Размещать новые файлы по году публикации."""
    return f"publications/{instance.publication.year or 'undated'}/{filename}"


class PublicationFile(models.Model):
    publication = models.ForeignKey(
        Publication, on_delete=models.CASCADE, related_name='files',
        verbose_name='Публикация',
    )
    file = models.FileField(
        'Файл', storage=publication_file_storage, upload_to=publication_file_path,
        max_length=500,
    )

    class Meta:
        verbose_name = 'Файл публикации'
        verbose_name_plural = 'Файлы публикации'
        ordering = ('pk',)

    @property
    def filename(self):
        return Path(self.file.name).name if self.file.name else ''

    def __str__(self):
        return self.filename

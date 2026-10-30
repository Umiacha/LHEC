from django.db import models

from research.models import diploma_file_path  # Совместимость с миграцией 0002.
from .storage import lecture_file_storage


class LabWork(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    short_description = models.TextField()
    equipment = models.TextField(blank=True)
    description = models.TextField(blank=True)

    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Лабораторная работа'
        verbose_name_plural = 'Лабораторные работы'


class TeachingMaterial(models.Model):
    class AccessLevel(models.TextChoices):
        PUBLIC = 'public', 'Для всех'
        INTERNAL = 'internal', 'Только для сотрудников'

    lab_work = models.ForeignKey(
        LabWork,
        on_delete=models.CASCADE,
        related_name='materials',
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='education/materials/')
    access_level = models.CharField(
        max_length=16,
        choices=AccessLevel.choices,
        default=AccessLevel.PUBLIC,
    )
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Учебный материал'
        verbose_name_plural = 'Учебные материалы'
        permissions = [
            ('view_internal_materials', 'Can view internal teaching materials'),
        ]


class LectureCourse(models.Model):
    """Курс лекций для сотрудников с правом view_internal_materials."""

    title = models.CharField('Название', max_length=255)
    slug = models.SlugField('Slug', max_length=255, unique=True)
    description = models.TextField('Описание', blank=True)
    lecturer = models.ForeignKey(
        'users.Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lecture_courses', verbose_name='Лектор',
    )
    order = models.PositiveIntegerField('Порядок отображения', default=0)
    is_published = models.BooleanField('Показывать на сайте', default=False)

    class Meta:
        verbose_name = 'Курс лекций'
        verbose_name_plural = 'Курсы лекций'
        ordering = ('order', 'pk')

    def __str__(self):
        return self.title


class Lecture(models.Model):
    """Лекция курса с примечанием лектора и произвольным числом вложений."""

    course = models.ForeignKey(
        LectureCourse, on_delete=models.CASCADE, related_name='lectures',
        verbose_name='Курс',
    )
    title = models.CharField('Название', max_length=255)
    note = models.TextField('Примечание лектора', blank=True)
    order = models.PositiveIntegerField('Порядок отображения', default=0)
    is_published = models.BooleanField('Показывать на сайте', default=False)
    updated_at = models.DateTimeField('Запись изменена', auto_now=True)

    class Meta:
        verbose_name = 'Лекция'
        verbose_name_plural = 'Лекции'
        ordering = ('order', 'pk')

    def __str__(self):
        return self.title


def lecture_file_path(instance, filename):
    return f'education/lectures/{instance.lecture_id}/{filename}'


class LectureFile(models.Model):
    """Презентация или дополнительный файл лекции в приватном хранилище."""

    lecture = models.ForeignKey(
        Lecture, on_delete=models.CASCADE, related_name='files',
        verbose_name='Лекция',
    )
    file = models.FileField(
        'Файл', upload_to=lecture_file_path, storage=lecture_file_storage,
        max_length=500,
        help_text='Просмотр и скачивание доступны только сотрудникам и администраторам.',
    )
    title = models.CharField('Подпись', max_length=255, blank=True)
    order = models.PositiveIntegerField('Порядок отображения', default=0)

    class Meta:
        verbose_name = 'Файл лекции'
        verbose_name_plural = 'Файлы лекций'
        ordering = ('order', 'pk')

    def __str__(self):
        return self.title or self.file.name.rsplit('/', 1)[-1]

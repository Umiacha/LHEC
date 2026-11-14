from django.utils.translation import gettext_lazy as _
from django.db import models

from core.i18n import localized_value
from core.fields import CanonicalSlugField

from research.models import diploma_file_path  # Совместимость с миграцией 0002.
from .storage import lecture_file_storage, teaching_material_file_storage


class LabWork(models.Model):
    title = models.CharField(max_length=255)
    slug = CanonicalSlugField(unique=True)
    short_description = models.TextField()
    equipment = models.TextField(blank=True)
    description = models.TextField(blank=True)

    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    short_description_en = models.TextField('Краткое описание — EN', blank=True)
    equipment_en = models.TextField('Оборудование — EN', blank=True)
    description_en = models.TextField('Описание — EN', blank=True)

    @property
    def localized_short_description(self):
        return localized_value(self, "short_description")

    @property
    def localized_equipment(self):
        return localized_value(self, "equipment")

    @property
    def localized_description(self):
        return localized_value(self, "description")

    title_en = models.CharField('Название — EN', max_length=255, blank=True)

    @property
    def localized_title(self):
        return localized_value(self, "title")

    class Meta:
        verbose_name = 'Лабораторная работа'
        verbose_name_plural = 'Лабораторные работы'


class TeachingMaterial(models.Model):
    class AccessLevel(models.TextChoices):
        PUBLIC = 'public', _('Для всех')
        INTERNAL = 'internal', _('Только для сотрудников')

    lab_work = models.ForeignKey(
        LabWork,
        on_delete=models.CASCADE,
        related_name='materials',
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='education/materials/', storage=teaching_material_file_storage)
    access_level = models.CharField(
        max_length=16,
        choices=AccessLevel.choices,
        default=AccessLevel.PUBLIC,
    )
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    description_en = models.TextField('Описание — EN', blank=True)

    @property
    def localized_description(self):
        return localized_value(self, "description")

    title_en = models.CharField('Название — EN', max_length=255, blank=True)

    @property
    def localized_title(self):
        return localized_value(self, "title")

    def get_download_url(self):
        from django.urls import reverse
        return reverse('education:download_material', kwargs={'pk': self.pk})

    class Meta:
        verbose_name = 'Учебный материал'
        verbose_name_plural = 'Учебные материалы'
        permissions = [
            ('view_internal_materials', 'Can view internal teaching materials'),
        ]


class LectureCourse(models.Model):
    """Курс лекций для сотрудников с правом view_internal_materials."""

    title = models.CharField('Название', max_length=255)
    slug = CanonicalSlugField('Slug', max_length=255, unique=True)
    description = models.TextField('Описание', blank=True)
    lecturer = models.ForeignKey(
        'users.Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lecture_courses', verbose_name='Лектор',
    )
    order = models.PositiveIntegerField('Порядок отображения', default=0)
    is_published = models.BooleanField('Показывать на сайте', default=False)

    description_en = models.TextField('Описание — EN', blank=True)

    @property
    def localized_description(self):
        return localized_value(self, "description")

    title_en = models.CharField('Название — EN', max_length=255, blank=True)

    @property
    def localized_title(self):
        return localized_value(self, "title")

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

    note_en = models.TextField('Примечание лектора — EN', blank=True)

    @property
    def localized_note(self):
        return localized_value(self, "note")

    title_en = models.CharField('Название — EN', max_length=255, blank=True)

    @property
    def localized_title(self):
        return localized_value(self, "title")

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

    title_en = models.CharField('Подпись — EN', max_length=255, blank=True)

    @property
    def localized_title(self):
        return localized_value(self, "title")

    @property
    def localized_label(self):
        return self.localized_title or self.file.name.rsplit("/", 1)[-1]

    class Meta:
        verbose_name = 'Файл лекции'
        verbose_name_plural = 'Файлы лекций'
        ordering = ('order', 'pk')

    def __str__(self):
        return self.title or self.file.name.rsplit('/', 1)[-1]


class StudentWorkTopic(models.Model):
    """Редактируемый архив тем дипломных и курсовых работ."""

    class Kind(models.TextChoices):
        DIPLOMA = 'diploma', _('Дипломная работа')
        COURSE = 'course', _('Курсовая работа')

    class Subject(models.TextChoices):
        INORGANIC = 'inorganic', _('Неорганическая химия')
        ANALYTICAL = 'analytical', _('Аналитическая химия')
        ORGANIC = 'organic', _('Органическая химия')
        PHYSICAL = 'physical', _('Физическая химия')
        MOLECULAR = 'molecular', _('Строение молекул')

    title = models.CharField('Название — RU', max_length=1000)
    title_en = models.CharField('Название — EN', max_length=1000, blank=True)
    kind = models.CharField('Вид работы', max_length=20, choices=Kind.choices)
    subject = models.CharField('Раздел', max_length=20, choices=Subject.choices, blank=True)
    sort_order = models.PositiveIntegerField('Порядок отображения', default=0)
    is_published = models.BooleanField('Показывать на сайте', default=True)

    class Meta:
        verbose_name = 'Тема дипломной или курсовой работы'
        verbose_name_plural = 'Темы дипломных и курсовых работ'
        ordering = ('sort_order', 'pk')

    @property
    def localized_title(self):
        return localized_value(self, 'title')

    def __str__(self):
        return self.title

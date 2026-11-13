from django.utils.translation import gettext_lazy as _
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator

from core.i18n import localized_value


class SciencePosition(models.TextChoices):
    """
    Научно-исследовательские должности.
    
    Порядок перечисления полей должен быть в порядке убывания иерархии.
    """
    HEAD_OF_THE_LABORATORY = 'head_of_the_laboratory', _('зав. лаб.')
    DEPUTY_HEAD_OF_THE_LABORATORY = 'deputy_head_of_the_laboratory', _('зам. зав. лаб.')
    LEADING_RESEARCH_FELLOW = 'leading_research_fellow', _('в.н.с.')
    SENIOR_RESEARCH_FELLOW = 'senior_research_fellow', _('с.н.с.')
    RESEARCH_FELLOW = 'research_fellow', _('н.с.')
    JUNIOR_RESEARCH_FELLOW = 'junior_research_fellow', _('м.н.с.')


class EngineerPosition(models.TextChoices):
    """
    Инженерно-технические должности.
    
    Порядок перечисления полей должен быть в порядке убывания иерархии.
    """
    LEADING_ENGINEER = 'leading_engineer', _('вед.инж.')
    SENIOR_ENGINEER = 'senior_engineer', _('ст.инж.')
    TECHNICIAN = 'technician', _('техн.')


class AcademicDegree(models.TextChoices):
    # CANDIDATE = 'candidate', 'к.н. (отрасль не указана)'
    CANDIDATE_CHEMISTRY = 'candidate_chemistry', _('к.х.н.')
    CANDIDATE_PHYS_MATH = 'candidate_phys_math', _('к.ф.-м.н.')
    CANDIDATE_BIOLOGY = 'candidate_biology', _('к.б.н.')
    # DOCTOR = 'doctor', 'д.н. (отрасль не указана)'
    DOCTOR_CHEMISTRY = 'doctor_chemistry', _('д.х.н.')
    DOCTOR_PHYS_MATH = 'doctor_phys_math', _('д.ф.-м.н.')

    @classmethod
    def candidates(cls):
        return [degree.value for degree in cls if degree.value.startswith('candidate')]

    @classmethod
    def doctors(cls):
        return [degree.value for degree in cls if degree.value.startswith('doctor')]


class AcademicTitle(models.TextChoices):
    DOCENT = 'docent', _('доц.')
    PROFESSOR = 'professor', _('проф.')


class EducationStatus(models.TextChoices):
    STUDENT = 'student', _('Студент')
    POSTGRADUATE = 'postgraduate', _('Аспирант')


class EmployeeQuerySet(models.QuerySet):
    def current(self):
        """Действующие участники независимо от видимости карточки."""
        return self.filter(is_current=True)

    def staff(self):
        """Сотрудники, включая обучающихся с должностью."""
        return self.filter(
            models.Q(education_status='')
            | ~models.Q(science_position='')
            | ~models.Q(engineer_position='')
        )

    def published(self):
        """Получение только опубликованных Employee."""
        return self.filter(is_published=True)

    def by_position(self):
        """
        Сортированный список сотрудников.
        
        Правило: научные сотрудники (по иерархии в порядке SciencePosition),
        затем -- инженеры (по иерархии в порядке SciencePosition).
        """
        rank = models.Case(
            *[
                models.When(science_position=position.value, then=models.Value(index))
                for index, position in enumerate(SciencePosition)
            ],
            *[
                models.When(
                    engineer_position=position.value,
                    then=models.Value(len(SciencePosition) + index),
                )
                for index, position in enumerate(EngineerPosition)
            ],
            default=models.Value(len(SciencePosition) + len(EngineerPosition)),
            output_field=models.IntegerField(),
        )
        return self.annotate(position_rank=rank).order_by(
            "position_rank", "last_name", "first_name", "mid_name", "pk"
        )


class Employee(models.Model):
    """Публичная карточка участника лаборатории с необязательным аккаунтом."""
    last_name = models.CharField(verbose_name='Фамилия', max_length=200)
    first_name = models.CharField(verbose_name='Имя', max_length=200)
    mid_name = models.CharField(verbose_name='Отчество', max_length=200, blank=True)
    photo = models.ImageField(verbose_name='Фото',upload_to='employees/photos/', blank=True)
    science_position = models.CharField(
        verbose_name='Научная должность',
        max_length=50,
        choices=SciencePosition.choices,
        blank=True
    )
    engineer_position = models.CharField(
        verbose_name='Инженерная должность',
        max_length=50,
        choices=EngineerPosition.choices,
        blank=True
    )
    education_status = models.CharField(
        'Статус обучения', max_length=20, choices=EducationStatus.choices,
        blank=True, default='',
    )
    study_year = models.PositiveSmallIntegerField(
        'Курс', null=True, blank=True, validators=[MinValueValidator(1)],
        help_text='Только для студентов. Обновляется вручную.',
    )
    academic_degree = models.CharField(
        'Учёная степень', max_length=20, choices=AcademicDegree.choices, blank=True,
    )
    academic_title = models.CharField(
        'Учёное звание', max_length=20, choices=AcademicTitle.choices, blank=True,
        help_text='Учёное звание, а не занимаемая должность.',
    )
    is_current = models.BooleanField(
        'Действующий участник', default=True,
        help_text='Снимите для бывшего участника. Не влияет на публикацию карточки и доступ к аккаунту.',
    )
    bio = models.TextField(verbose_name='Описание', blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employee_profile',
        verbose_name='Аккаунт',
    )
    is_published = models.BooleanField(verbose_name='Опубликовано', default=True)
    objects = EmployeeQuerySet.as_manager()

    last_name_en = models.CharField('Фамилия — EN', max_length=200, blank=True)
    first_name_en = models.CharField('Имя — EN', max_length=200, blank=True)
    mid_name_en = models.CharField('Отчество — EN', max_length=200, blank=True)
    bio_en = models.TextField('Описание — EN', blank=True)

    @property
    def localized_last_name(self):
        return localized_value(self, "last_name")

    @property
    def localized_first_name(self):
        return localized_value(self, "first_name")

    @property
    def localized_mid_name(self):
        return localized_value(self, "mid_name")

    @property
    def localized_bio(self):
        return localized_value(self, "bio")

    @property
    def localized_full_name(self):
        return ' '.join(filter(None, (
            self.localized_last_name, self.localized_first_name, self.localized_mid_name,
        )))

    class Meta:
        verbose_name = 'Карточка участника лаборатории'
        verbose_name_plural = 'Карточки участников лаборатории'

    def clean(self):
        super().clean()
        if self.study_year is not None and self.education_status != EducationStatus.STUDENT:
            raise ValidationError({'study_year': 'Курс можно указать только для студента.'})

    @property
    def education_label(self):
        label = self.get_education_status_display()
        if self.education_status == EducationStatus.STUDENT and self.study_year is not None:
            return _('%(status)s, %(year)s курс') % {'status': label, 'year': self.study_year}
        return label

    def __str__(self):
        return f'{self.last_name} {self.first_name}'.strip()


class ScientificProfile(models.Model):
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='scientific_profiles',
        verbose_name='Сотрудник',
    )
    url = models.URLField('URL', max_length=500)
    sort_order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Научный профиль'
        verbose_name_plural = 'Научные профили'
        ordering = ('sort_order', 'pk')
        constraints = [models.UniqueConstraint(
            fields=('employee', 'url'), name='unique_employee_scientific_profile',
        )]

    def __str__(self):
        return self.url

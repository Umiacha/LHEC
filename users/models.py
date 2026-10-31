from django.db import models
from django.conf import settings


class SciencePosition(models.TextChoices):
    """
    Научно-исследовательские должности.
    
    Порядок перечисления полей должен быть в порядке убывания иерархии.
    """
    HEAD_OF_THE_LABORATORY = 'head_of_the_laboratory', 'зав. лаб.'
    DEPUTY_HEAD_OF_THE_LABORATORY = 'deputy_head_of_the_laboratory', 'зам. зав. лаб.'
    LEADING_RESEARCH_FELLOW = 'leading_research_fellow', 'в.н.с.'
    SENIOR_RESEARCH_FELLOW = 'senior_research_fellow', 'с.н.с.'
    RESEARCH_FELLOW = 'research_fellow', 'н.с.'
    JUNIOR_RESEARCH_FELLOW = 'junior_research_fellow', 'м.н.с.'


class EngineerPosition(models.TextChoices):
    """
    Инженерно-технические должности.
    
    Порядок перечисления полей должен быть в порядке убывания иерархии.
    """
    LEADING_ENGINEER = 'leading_engineer', 'вед.инж.'
    SENIOR_ENGINEER = 'senior_engineer', 'ст.инж.'
    TECHNICIAN = 'technician', 'техн.'


class AcademicDegree(models.TextChoices):
    # CANDIDATE = 'candidate', 'к.н. (отрасль не указана)'
    CANDIDATE_CHEMISTRY = 'candidate_chemistry', 'к.х.н.'
    CANDIDATE_PHYS_MATH = 'candidate_phys_math', 'к.ф.-м.н.'
    CANDIDATE_BIOLOGY = 'candidate_biology', 'к.б.н.'
    # DOCTOR = 'doctor', 'д.н. (отрасль не указана)'
    DOCTOR_CHEMISTRY = 'doctor_chemistry', 'д.х.н.'
    DOCTOR_PHYS_MATH = 'doctor_phys_math', 'д.ф.-м.н.'

    @classmethod
    def candidates(cls):
        return [degree.value for degree in cls if degree.value.startswith('candidate')]

    @classmethod
    def doctors(cls):
        return [degree.value for degree in cls if degree.value.startswith('doctor')]


class AcademicTitle(models.TextChoices):
    DOCENT = 'docent', 'доц.'
    PROFESSOR = 'professor', 'проф.'


class EmployeeQuerySet(models.QuerySet):
    def current(self):
        """Действующие сотрудники независимо от видимости карточки."""
        return self.filter(is_current=True)

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


# TODO: Добавить статус "студент/аспирант" (мб еще кто?), кроме научной и инженерной должностей.
class Employee(models.Model):  # TODO: сделать ссылки на istina.msu и пр., а также связь с научной группой и публикациями.
    """Модель данных сотрудника."""
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
    academic_degree = models.CharField(
        'Учёная степень', max_length=20, choices=AcademicDegree.choices, blank=True,
    )
    academic_title = models.CharField(
        'Учёное звание', max_length=20, choices=AcademicTitle.choices, blank=True,
        help_text='Учёное звание, а не занимаемая должность.',
    )
    is_current = models.BooleanField(
        'Действующий сотрудник', default=True,
        help_text='Снимите для бывшего сотрудника. Не влияет на публикацию карточки и доступ к аккаунту.',
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

    def __str__(self):
        return f'{self.last_name} {self.first_name}'.strip()

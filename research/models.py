from django.core.validators import MinValueValidator
from django.db import models
from .storage import dissertation_file_storage, diploma_file_storage


class ResearchDirection(models.Model):  # TODO: сделать отображения карточек сотрудников, а не просто ФИО
    """Научное направление и работающая в нём научная группа."""

    name = models.CharField('Название', max_length=255)
    slug = models.SlugField('Slug', max_length=255, unique=True)
    description = models.TextField('Описание', blank=True)
    leader = models.ForeignKey(
        'users.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='led_research_directions',
        verbose_name='Руководитель',
    )
    employees = models.ManyToManyField(
        'users.Employee',
        blank=True,
        related_name='research_directions',
        through='ResearchMembership',
        verbose_name='Участники',
        help_text='Руководитель входит в команду автоматически; добавлять его здесь необязательно.',
    )
    sort_order = models.PositiveIntegerField('Порядок отображения', default=0)
    is_published = models.BooleanField('Показывать на сайте', default=False)
    created_at = models.DateTimeField('Запись создана', auto_now_add=True)
    updated_at = models.DateTimeField('Запись изменена', auto_now=True)

    class Meta:
        verbose_name = 'Научное направление'
        verbose_name_plural = 'Научные направления'
        ordering = ('sort_order', 'name', 'pk')

    def __str__(self):
        return self.name

    def get_team(self):
        """Полный состав группы, включая руководителя, без повторений."""
        from users.models import Employee

        return Employee.objects.filter(
            models.Q(research_directions=self) | models.Q(pk=self.leader_id)
        ).distinct()


class ResearchMembership(models.Model):
    """Участие сотрудника в научном направлении."""

    direction = models.ForeignKey(
        ResearchDirection,
        on_delete=models.CASCADE,
        related_name='memberships',
        verbose_name='Научное направление',
    )
    employee = models.ForeignKey(
        'users.Employee',
        on_delete=models.CASCADE,
        related_name='research_memberships',
        verbose_name='Сотрудник',
    )

    class Meta:
        verbose_name = 'Участие в научном направлении'
        verbose_name_plural = 'Участники научных направлений'
        unique_together = (('direction', 'employee'),)

    def __str__(self):
        return f'{self.employee} — {self.direction}'


class ResearchProject(models.Model):
    """Научный проект и реквизиты его финансирования."""

    class FundingKind(models.TextChoices):
        GRANT = 'grant', 'Грант'
        CONTRACT = 'contract', 'Договор'
        STATE_ASSIGNMENT = 'state_assignment', 'Государственное задание'
        OTHER = 'other', 'Другое'

    name = models.CharField('Название', max_length=500)
    slug = models.SlugField('Slug', max_length=255, unique=True)
    start_year = models.PositiveSmallIntegerField('Год начала')
    end_year = models.PositiveSmallIntegerField('Год окончания')
    abstract = models.TextField('Аннотация', blank=True)
    research_directions = models.ManyToManyField(
        ResearchDirection, blank=True, related_name='projects',
        verbose_name='Научные направления',
    )
    funding_source = models.CharField('Источник финансирования', max_length=500, blank=True)
    customer = models.CharField('Заказчик', max_length=500, blank=True)
    funding_kind = models.CharField('Тип основания', max_length=20, choices=FundingKind.choices, blank=True)
    funding_number = models.CharField('Номер гранта, договора или задания', max_length=255, blank=True)
    funding_program = models.CharField('Программа или конкурс', max_length=500, blank=True)
    external_url = models.URLField('Внешняя страница проекта', blank=True)
    is_published = models.BooleanField('Показывать на сайте', default=False)
    sort_order = models.PositiveIntegerField('Порядок отображения', default=0)
    created_at = models.DateTimeField('Запись создана', auto_now_add=True)
    updated_at = models.DateTimeField('Запись изменена', auto_now=True)

    class Meta:
        verbose_name = 'Научный проект'
        verbose_name_plural = 'Научные проекты'
        ordering = ('-start_year', 'sort_order', 'name', 'pk')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(start_year__gte=1, end_year__gte=models.F('start_year')),
                name='research_project_valid_years',
            ),
        ]

    def __str__(self):
        return self.name


class ProjectParticipation(models.Model):
    """Участие в научном проекте."""

    class Role(models.TextChoices):
        LEADER = 'leader', 'Руководитель'
        EXECUTOR = 'executor', 'Основной исполнитель'

    project = models.ForeignKey(
        ResearchProject, on_delete=models.CASCADE, related_name='participations',
        verbose_name='Проект',
    )
    employee = models.ForeignKey(
        'users.Employee', on_delete=models.PROTECT, null=True, blank=True,
        related_name='project_participations', verbose_name='Сотрудник ЛХВЭ',
    )
    external_name = models.CharField('ФИО внешнего участника', max_length=255, blank=True)
    external_organization = models.CharField('Организация внешнего участника', max_length=500, blank=True)
    role = models.CharField('Роль', max_length=20, choices=Role.choices, default=Role.EXECUTOR)
    sort_order = models.PositiveIntegerField('Порядок отображения', default=0)

    class Meta:
        verbose_name = 'Участие в научном проекте'
        verbose_name_plural = 'Участия в научных проектах'
        ordering = ('sort_order', 'pk')
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(employee__isnull=False, external_name='', external_organization='')
                    | (models.Q(employee__isnull=True) & ~models.Q(external_name=''))
                ),
                name='research_project_participant_identity',
            ),
            models.UniqueConstraint(
                fields=('project',), condition=models.Q(role='leader'),
                name='research_project_one_leader',
            ),
            models.UniqueConstraint(
                fields=('project', 'employee'), condition=models.Q(employee__isnull=False),
                name='research_project_unique_employee',
            ),
            models.UniqueConstraint(
                fields=('project', 'external_name', 'external_organization'),
                condition=models.Q(employee__isnull=True),
                name='research_project_unique_external',
            ),
        ]

    def clean(self):
        super().clean()
        self.external_name = self.external_name.strip()
        self.external_organization = self.external_organization.strip()

    def __str__(self):
        person = str(self.employee) if self.employee_id else self.external_name
        return f'{person} — {self.project}'


def dissertation_file_path(instance, filename):
    return f'dissertations/{instance.year}/{filename}'


class Dissertation(models.Model):
    """Защищённая в лаборатории диссертация."""

    class Degree(models.TextChoices):
        CANDIDATE = 'candidate', 'Кандидатская диссертация'
        DOCTOR = 'doctor', 'Докторская диссертация'

    title = models.CharField('Название', max_length=1000)
    external_url = models.URLField('Внешняя страница диссертации', max_length=1000)
    author = models.CharField('Автор (ФИО)', max_length=255)
    year = models.PositiveSmallIntegerField('Год защиты', validators=[MinValueValidator(1)])
    degree = models.CharField('Вид диссертации', max_length=20, choices=Degree.choices, default=Degree.CANDIDATE)
    specialty = models.CharField('Шифр и название специальности', max_length=500, blank=True)
    supervisors = models.CharField('Научные руководители / консультанты', max_length=1000, blank=True)
    file = models.FileField(
        'Текст диссертации', upload_to=dissertation_file_path,
        storage=dissertation_file_storage, blank=True,
        help_text='Скачивание доступно только сотрудникам и администраторам.',
    )
    is_published = models.BooleanField('Показывать на сайте', default=False)
    sort_order = models.PositiveIntegerField('Порядок отображения', default=0)

    class Meta:
        verbose_name = 'Диссертация'
        verbose_name_plural = 'Диссертации'
        ordering = ('-year', 'sort_order', 'author', 'pk')

    def __str__(self):
        return f'{self.author} — {self.title}'


def diploma_file_path(instance, filename):
    return f'diplomas/{instance.year}/{filename}'


class Diploma(models.Model):
    """Защищённая выпускная квалификационная работа."""

    class Level(models.TextChoices):
        BACHELOR = 'bachelor', 'Бакалаврская работа'
        MASTER = 'master', 'Магистерская диссертация'
        SPECIALIST = 'specialist', 'Дипломная работа специалиста'

    title = models.CharField('Название', max_length=1000)
    external_url = models.URLField('Внешняя страница работы', max_length=1000)
    author = models.ForeignKey(
        'users.Employee', on_delete=models.PROTECT, related_name='diplomas',
        verbose_name='Автор',
    )
    year = models.PositiveSmallIntegerField('Год защиты', validators=[MinValueValidator(1)])
    level = models.CharField('Уровень работы', max_length=20, choices=Level.choices)
    supervisors = models.ManyToManyField(
        'users.Employee', blank=True, related_name='supervised_diplomas',
        verbose_name='Научные руководители',
    )
    external_supervisors = models.CharField(
        'ФИО внешних научных руководителей', max_length=1000, blank=True,
        help_text='Для руководителей, у которых нет карточки на сайте.',
    )
    file = models.FileField(
        'Текст работы', upload_to=diploma_file_path, storage=diploma_file_storage,
        blank=True, help_text='Скачивание доступно только сотрудникам и администраторам.',
    )
    is_published = models.BooleanField('Показывать на сайте', default=False)
    sort_order = models.PositiveIntegerField('Порядок отображения', default=0)

    class Meta:
        verbose_name = 'Выпускная квалификационная работа'
        verbose_name_plural = 'Выпускные квалификационные работы'
        ordering = ('-year', 'sort_order', 'pk')

    def __str__(self):
        return f'{self.author} — {self.title}'

from django.db import models


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

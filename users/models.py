from django.db import models


class SciencePositions(models.TextChoices):
    """Научно-исследовательские должности."""
    HEAD_OF_THE_LABORATORY = 'head_of_the_laboratory', 'зав. лаб.'
    DEPUTY_HEAD_OF_THE_LABORATORY = 'deputy_head_of_the_laboratory', 'зам. зав. лаб.'
    LEADING_RESEARCH_FELLOW = 'leading_research_fellow', 'в.н.с.'
    SENIOR_RESEARCH_FELLOW = 'senior_research_fellow', 'с.н.с.'
    RESEARCH_FELLOW = 'research_fellow', 'н.с.'
    JUNIOR_RESEARCH_FELLOW = 'junior_research_fellow', 'м.н.с.'


class EngineerPositions(models.TextChoices):
    """Инженерно-технические должности."""
    LEADING_ENGINEER = 'leading_engineer', 'вед.инж.'
    SENIOR_ENGINEER = 'senior_engineer', 'ст.инж.'
    TECHNICIAN = 'technician', 'техн.'


class Employee(models.Model):
    """Модель данных сотрудника."""
    last_name = models.CharField(verbose_name='Фамилия', max_length=200)
    first_name = models.CharField(verbose_name='Имя', max_length=200)
    mid_name = models.CharField(verbose_name='Отчество', max_length=200, blank=True)
    science_position = models.CharField(
        verbose_name='Научная должность',
        max_length=50,
        choices=SciencePositions.choices,
        blank=True
    )
    engineer_position = models.CharField(
        verbose_name='Научная должность',
        max_length=50,
        choices=EngineerPositions.choices,
        blank=True
    )

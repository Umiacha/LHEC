from django.db import models


class Publication(models.Model):
    """Научная публикация."""
    class Kind(models.TextChoices):
        ARTICLE = 'article', 'Статья'
        CONFERENCE = 'conference', 'Материалы конференции'
        BOOK = 'book', 'Книга'
        CHAPTER = 'chapter', 'Глава в книге'
        OTHER = 'other', 'Другое'

    title = models.CharField(verbose_name='Название', max_length=500)
    year = models.PositiveSmallIntegerField(verbose_name='Год')
    authors_text = models.TextField(verbose_name='Авторы')
    employees = models.ManyToManyField(
        'users.Employee',
        blank=True,
        related_name='publications',
        verbose_name='Сотрудники лаборатории среди авторов'
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
    created_at = models.DateTimeField('Запись создана', auto_now_add=True)
    updated_at = models.DateTimeField('Запись изменена', auto_now=True)

    class Meta:
        verbose_name = 'Публикация'
        verbose_name_plural = 'Публикации'
        ordering = ('-year', '-id')

    def __str__(self):
        return f'{self.authors_text}: {self.title} ({self.year})'

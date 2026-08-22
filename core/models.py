from django.db import models
from django.utils import timezone


class Announcement(models.Model):
    title = models.CharField(
        'Заголовок',
        max_length=200,
    )
    text = models.TextField(
        'Текст',
    )
    is_published = models.BooleanField(
        'Опубликовано',
        default=False,
    )
    published_at = models.DateTimeField(
        'Дата публикации',
        default=timezone.now
    )
    created_at = models.DateTimeField(
        'Создано',
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        'Изменено',
        auto_now=True,
    )

    class Meta:
        verbose_name = 'Объявление'
        verbose_name_plural = 'Объявления'
        ordering = ('-published_at',)

    def __str__(self) -> str:
        return self.title

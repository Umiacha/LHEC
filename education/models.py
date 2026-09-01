from django.db import models


class LabWork(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    short_description = models.TextField()
    equipment = models.TextField(blank=True)
    description = models.TextField(blank=True)

    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)


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
        permissions = [
            ('view_internal_materials', 'Can view internal teaching materials'),
        ]
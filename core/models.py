from io import BytesIO

from django.core.files.base import ContentFile
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from PIL import Image, ImageOps

from .i18n import localized_value
from .gallery import gallery_image_path, gallery_thumbnail_path, validate_gallery_image

from django.db import models
from django.utils import timezone


class Announcement(models.Model):  # TODO: добавляем ли эту инфу на страницы науч. направлений? Сотрудников?
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

    title_en = models.CharField('Заголовок — EN', max_length=200, blank=True)
    text_en = models.TextField('Текст — EN', blank=True)

    @property
    def localized_title(self):
        return localized_value(self, "title")

    @property
    def localized_text(self):
        return localized_value(self, "text")

    class Meta:
        verbose_name = 'Объявление'
        verbose_name_plural = 'Объявления'
        ordering = ('-published_at',)

    def __str__(self) -> str:
        return self.title


class GalleryPhoto(models.Model):
    image = models.ImageField(
        'Фотография', upload_to=gallery_image_path,
        validators=[validate_gallery_image],
        help_text='JPEG, PNG или WebP; до 20 МБ и 40 мегапикселей.',
    )
    thumbnail = models.ImageField(
        'Миниатюра', upload_to=gallery_thumbnail_path, editable=False,
    )
    caption = models.CharField('Подпись', max_length=500)
    year = models.PositiveSmallIntegerField(
        'Год фотографии', validators=[MinValueValidator(1), MaxValueValidator(9999)],
        help_text='Год съёмки, в том числе для архивных фотографий. '
                  'Изменение года не перемещает ранее загруженные файлы.',
    )
    order = models.PositiveIntegerField('Порядок', default=0)
    is_published = models.BooleanField('Показывать на сайте', default=False)
    created_at = models.DateTimeField('Добавлено', auto_now_add=True)
    updated_at = models.DateTimeField('Изменено', auto_now=True)

    caption_en = models.CharField('Подпись — EN', max_length=500, blank=True)

    @property
    def localized_caption(self):
        return localized_value(self, "caption")

    class Meta:
        verbose_name = 'Фотография галереи'
        verbose_name_plural = 'Фотографии галереи'
        ordering = ('order', '-year', '-created_at', '-pk')

    def __str__(self):
        return self.caption

    def save(self, *args, **kwargs):
        old = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        update_fields = kwargs.get('update_fields')
        image_changed = (update_fields is None or 'image' in update_fields) and (
            not old or self.image.name != old.image.name or not self.image._committed
        )
        if image_changed:
            validate_gallery_image(self.image)
            self.image.open('rb')
            try:
                with Image.open(self.image) as source:
                    preview = ImageOps.exif_transpose(source)
                    preview.thumbnail((960, 960))
                    # Composite transparency onto white before creating the JPEG preview.
                    rgba = preview.convert('RGBA')
                    background = Image.new('RGB', rgba.size, 'white')
                    background.paste(rgba, mask=rgba.getchannel('A'))
                    output = BytesIO()
                    background.save(output, format='JPEG', quality=85, optimize=True)
                self.thumbnail.save('preview.jpg', ContentFile(output.getvalue()), save=False)
            finally:
                self.image.seek(0)
            if update_fields is not None:
                kwargs['update_fields'] = set(update_fields) | {'thumbnail'}
        super().save(*args, **kwargs)
        if old:
            for field in ('image', 'thumbnail'):
                previous = getattr(old, field)
                if previous and previous.name != getattr(self, field).name:
                    transaction.on_commit(
                        lambda file=previous: file.storage.delete(file.name)
                    )


@receiver(post_delete, sender=GalleryPhoto)
def delete_gallery_files(sender, instance, **kwargs):
    for file in (instance.image, instance.thumbnail):
        if file:
            transaction.on_commit(lambda file=file: file.storage.delete(file.name))

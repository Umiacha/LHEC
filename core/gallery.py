"""Paths and validation for public gallery uploads."""
from pathlib import Path
from uuid import uuid4

from django.core.exceptions import ValidationError
from PIL import Image

MAX_PHOTO_BYTES = 20 * 1024 * 1024


def gallery_image_path(instance, filename):
    return f'gallery/{instance.year}/{uuid4().hex}{Path(filename).suffix.lower()}'


def gallery_thumbnail_path(instance, filename):
    return f'gallery/{instance.year}/thumbnails/{uuid4().hex}.jpg'


def validate_gallery_image(value):
    if value.size > MAX_PHOTO_BYTES:
        raise ValidationError('Размер фотографии не должен превышать 20 МБ.')
    try:
        value.open('rb')
        with Image.open(value) as image:
            if image.format not in {'JPEG', 'PNG', 'WEBP'}:
                raise ValidationError('Загрузите фотографию в формате JPEG, PNG или WebP.')
            if image.width * image.height > 40_000_000:
                raise ValidationError('Разрешение фотографии не должно превышать 40 мегапикселей.')
            image.verify()
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValidationError('Не удалось прочитать изображение.') from exc
    finally:
        value.seek(0)

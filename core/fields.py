"""String policies shared by models, forms and literal ORM writes."""

import unicodedata

from django.db import models


TEXT_COLLATION = 'utf8mb4_0900_as_ci'


class NormalizedNameField(models.CharField):
    """Preserve spelling and accents; normalize composition and outer whitespace."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('db_collation', TEXT_COLLATION)
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        value = super().to_python(value)
        return unicodedata.normalize('NFC', value).strip() if value is not None else None

    def pre_save(self, model_instance, add):
        value = self.to_python(super().pre_save(model_instance, add))
        setattr(model_instance, self.attname, value)
        return value


class CanonicalSlugField(models.SlugField):
    """ASCII slugs are stored in lowercase, with case-insensitive uniqueness."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('db_collation', TEXT_COLLATION)
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        value = super().to_python(value)
        return value.strip().lower() if value is not None else None

    def pre_save(self, model_instance, add):
        value = self.to_python(super().pre_save(model_instance, add))
        setattr(model_instance, self.attname, value)
        return value

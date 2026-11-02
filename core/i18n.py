"""Language selection for database content shared by public models."""

from django.utils.translation import get_language


def localized_value(instance, field):
    """Use a non-empty English translation, falling back to the Russian field."""
    if (get_language() or '').split('-')[0] == 'en':
        translated = getattr(instance, f'{field}_en')
        if translated.strip():
            return translated
    return getattr(instance, field)

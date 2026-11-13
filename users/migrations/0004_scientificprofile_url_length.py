from copy import copy

from django.db import migrations
from django.db.models.functions import Length


def check_url_lengths(apps, schema_editor):
    profiles = apps.get_model('users', 'ScientificProfile').objects.using(
        schema_editor.connection.alias,
    ).annotate(url_length=Length('url'))
    oversized = profiles.filter(url_length__gt=500)
    count = oversized.count()
    if count:
        raise RuntimeError(
            f'Нельзя сократить ScientificProfile.url до 500 символов: '
            f'найдено записей с более длинными URL: {count}. '
            'Сохраните исходные данные и исправьте ссылки перед повтором миграции. '
            'Значения не обрезаны.'
        )


def shrink_url(apps, schema_editor):
    profile = apps.get_model('users', 'ScientificProfile')
    field = profile._meta.get_field('url')
    old_field = copy(field)
    old_field.max_length = 2000
    # Explicitly alter the column even though the corrected 0003 state is already 500.
    schema_editor.alter_field(profile, old_field, field)


class Migration(migrations.Migration):
    atomic = False
    dependencies = [('users', '0003_scientificprofile')]

    operations = [
        migrations.RunPython(check_url_lengths, migrations.RunPython.noop),
        migrations.RunPython(shrink_url, migrations.RunPython.noop, atomic=False),
    ]

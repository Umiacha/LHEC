"""Pin standard auth.User columns without replacing or patching Django's model.

The auth migration state belongs to Django. Only its physical columns are changed
here; later Django upgrades must retain this schema policy.
"""

from copy import copy

from django.db import migrations
from django.db.models import Count
from django.db.models.functions import Collate


COLLATION = 'utf8mb4_0900_as_ci'


def check_collations_and_duplicates(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT COLLATION_NAME FROM information_schema.COLLATIONS '
            'WHERE COLLATION_NAME IN (%s, %s)',
            [COLLATION, 'utf8mb4_0900_bin'],
        )
        available = {row[0] for row in cursor.fetchall()}
    if available != {COLLATION, 'utf8mb4_0900_bin'}:
        raise RuntimeError('Требуется MySQL с utf8mb4_0900_as_ci и utf8mb4_0900_bin.')

    # Check before any DDL in this migration. Never expose identifier values.
    targets = [
        ('auth', 'User', ('username',)),
        ('research', 'ResearchDirection', ('slug',)),
        ('research', 'ResearchProject', ('slug',)),
        ('education', 'LabWork', ('slug',)),
        ('education', 'LectureCourse', ('slug',)),
        ('research', 'ProjectParticipation', ('external_name', 'external_organization')),
    ]
    for app_label, model_name, fields in targets:
        model = apps.get_model(app_label, model_name)
        rows = model.objects.using(connection.alias)
        grouping = []
        if model_name == 'ProjectParticipation':
            rows = rows.filter(employee_id__isnull=True)
            grouping.append('project_id')
        for index, field in enumerate(fields):
            alias = f'comparison_{index}'
            rows = rows.annotate(**{alias: Collate(field, COLLATION)})
            grouping.append(alias)
        if rows.order_by().values(*grouping).annotate(total=Count('pk')).filter(total__gt=1).exists():
            raise RuntimeError(
                f'Найдены дубликаты {app_label}.{model_name} по новым правилам сравнения. '
                'Сохраните данные и устраните совпадения перед повтором миграции. '
                'Значения не изменены.'
            )


def pin_auth_user_collations(apps, schema_editor):
    user = apps.get_model('auth', 'User')
    for name in ('username', 'first_name', 'last_name'):
        old_field = user._meta.get_field(name)
        new_field = copy(old_field)
        new_field.db_collation = COLLATION
        schema_editor.alter_field(user, old_field, new_field)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('core', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('users', '0005_alter_scientificprofile_url'),
        ('research', '0006_alter_diploma_external_url_and_more'),
        ('education', '0002_seed_student_work_topics'),
    ]

    operations = [
        migrations.RunPython(check_collations_and_duplicates, migrations.RunPython.noop),
        # Deliberately irreversible: restoring an inherited ai_ci collation can
        # merge now-distinct accented usernames and fail on the unique index.
        migrations.RunPython(pin_auth_user_collations),
    ]

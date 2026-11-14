"""Apply the project's comparison policy to Django's standard auth.User.

Django owns the auth model state; only the physical columns are changed here.
"""
from copy import copy

from django.db import migrations


def pin_auth_user_collations(apps, schema_editor):
    user = apps.get_model('auth', 'User')
    for name in ('username', 'first_name', 'last_name'):
        old_field = user._meta.get_field(name)
        new_field = copy(old_field)
        new_field.db_collation = 'utf8mb4_0900_as_ci'
        schema_editor.alter_field(user, old_field, new_field)


class Migration(migrations.Migration):
    atomic = False
    dependencies = [
        ('core', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]
    operations = [migrations.RunPython(pin_auth_user_collations)]

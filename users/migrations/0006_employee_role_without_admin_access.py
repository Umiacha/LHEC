from django.db import migrations


def remove_admin_access(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    User.objects.using(schema_editor.connection.alias).filter(
        groups__name='Сотрудники', is_superuser=False,
    ).update(is_staff=False)


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0005_alter_employee_options_employee_education_status_and_more'),
    ]

    operations = [migrations.RunPython(remove_admin_access, migrations.RunPython.noop)]

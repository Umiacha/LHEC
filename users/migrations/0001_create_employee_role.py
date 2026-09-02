from django.db import migrations


EMPLOYEE_GROUP_NAME = "Сотрудники"


def create_employee_role(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    content_type, _ = ContentType.objects.get_or_create(
        app_label="education",
        model="teachingmaterial",
    )

    permission, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename="view_internal_materials",
        defaults={
            "name": "Can view internal teaching materials",
        },
    )

    employee_group, _ = Group.objects.get_or_create(
        name=EMPLOYEE_GROUP_NAME,
    )

    employee_group.permissions.add(permission)


def delete_employee_role(apps, schema_editor):
    Group = apps.get_model("auth", "Group")

    Group.objects.filter(
        name=EMPLOYEE_GROUP_NAME,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("education", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            create_employee_role,
            delete_employee_role,
        ),
    ]
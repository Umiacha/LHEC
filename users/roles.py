from django.contrib.auth.models import Group, User
from django.db import models


class UserRole(models.TextChoices):
    ADMINISTRATOR = 'administrator', 'Администратор'
    EMPLOYEE = 'employee', 'Сотрудник'


EMPLOYEE_GROUP_NAME = 'Сотрудники'
INTERNAL_MATERIALS_PERMISSION = 'education.views_internal_materials'


def get_user_role(user: User) -> UserRole | None:
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return UserRole.ADMINISTRATOR
    if user.has_perm(INTERNAL_MATERIALS_PERMISSION):
        return UserRole.EMPLOYEE
    return None


def set_user_role(user: User, role: UserRole):
    """
    Назначить пользователю одну из UserRole.

    Администратор == Django superuser.
    Сотрудник == обычный пользователь группы 'Сотрудник'.
    """
    role = UserRole(role)
    employee_group = Group.objects.get(name=EMPLOYEE_GROUP_NAME)
    user.groups.clear()
    user.user_permissions.clear()
    if role == UserRole.ADMINISTRATOR:
        user.is_staff = True
        user.is_superuser = True
    elif role == UserRole.EMPLOYEE:
        user.is_staff = True
        user.is_superuser = False
    user.save(update_fields=['is_staff', 'is_superuser',])
    if role == UserRole.EMPLOYEE:
        user.group.add(employee_group)
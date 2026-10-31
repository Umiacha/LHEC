from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group, User

from .forms import RoleUserChangeForm, RoleUserCreationForm
from .roles import get_user_role, set_user_role
from .models import Employee


admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = RoleUserChangeForm
    add_form = RoleUserCreationForm

    list_display = (
        "username",
        "first_name",
        "last_name",
        "email",
        "role_display",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "username",
                    "password",
                )
            },
        ),
        (
            "Персональная информация",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "email",
                )
            },
        ),
        (
            "Доступ",
            {
                "fields": (
                    "role",
                    "is_active",
                )
            },
        ),
        (
            "Даты",
            {
                "fields": (
                    "last_login",
                    "date_joined",
                )
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "password1",
                    "password2",
                    "role",
                ),
            },
        ),
    )

    readonly_fields = (
        "last_login",
        "date_joined",
    )

    filter_horizontal = ()

    search_fields = (
        "username",
        "first_name",
        "last_name",
        "email",
    )

    ordering = (
        "username",
    )

    @admin.display(description="Роль")
    def role_display(self, obj):
        role = get_user_role(obj)

        if role is None:
            return "Без роли"

        return role.label

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        set_user_role(
            obj,
            form.cleaned_data["role"],
        )

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Employee)
class EmployeeProfileAdmin(admin.ModelAdmin):
    """
    Карточка сотрудника.
    
    Без обязательной привязки к аккаунту.
    """
    fieldsets = (
        ('Основное', {
            'fields': ('last_name', 'first_name', 'mid_name', 'photo'),
        }),
        ('Работа и описание', {
            'fields': ('science_position', 'engineer_position', 'academic_degree',
                       'academic_title', 'is_current', 'bio'),
        }),
        ('Аккаунт и публикации', {
            'fields': ('user', 'is_published'),
        }),
    )
    list_display = (
        'last_name',
        'first_name',
        'science_position',
        'engineer_position',
        'academic_degree',
        'academic_title',
        'is_current',
        'user',
        'is_published',
    )
    list_filter = ("is_current", "is_published", "academic_degree", "academic_title",
                   "science_position", "engineer_position")
    search_fields = ("last_name", "first_name", "mid_name", "user__username")
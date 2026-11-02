from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    UserChangeForm,
    UserCreationForm,
)
from django.contrib.auth.models import User
from .roles import UserRole, get_user_role
from .models import Employee


INPUT_CLASSES = 'form-control'


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label='Логин',
        widget=forms.TextInput(
            attrs={
                'class': INPUT_CLASSES,
                'autocomplete': 'username',
                'autofocus': True,
            }
        ),
    )
    password = forms.CharField(
        label='Пароль',
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                'class': INPUT_CLASSES,
                'autocomplete': 'current-password',
            }
        ),
    )


class RoleUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(
        label='Роль',
        choices=UserRole.choices,
        initial=UserRole.EMPLOYEE,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username',)


class RoleUserChangeForm(UserChangeForm):
    role = forms.ChoiceField(
            label='Роль',
            choices=UserRole.choices,
        )

    class Meta(UserChangeForm.Meta):
        model = User

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        role = get_user_role(self.instance)
        if role is not None:
            self.fields['role'].initial = role


class EmployeeEditForm(forms.ModelForm):
    """Форма для изменения своей карточки сотрудником на сайте."""

    class Meta:
        model = Employee
        fields = ('last_name', 'first_name', 'mid_name', 'photo', 'bio')
        widgets = {
            'last_name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'first_name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'mid_name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'photo': forms.ClearableFileInput(attrs={
                'class': 'file-control',
                'accept': 'image/*',
            }),
            'bio': forms.Textarea(attrs={'class': INPUT_CLASSES, 'rows': 8}),
        }

from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    UserChangeForm,
    UserCreationForm,
)
from django.contrib.auth.models import User
from .roles import UserRole, get_user_role


INPUT_CLASSES = (
    "mt-2 block w-full rounded-xl border border-slate-300 "
    "bg-white px-4 py-3 text-sm text-slate-900 outline-none "
    "transition focus:border-energy-500 focus:ring-2 "
    "focus:ring-energy-500/20"
)


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
    role = forms.CharField(
        label='Роль',
        choices=UserRole.choices,
        initial=UserRole.EMPLOYEE,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username',)


class RoleUserChangeForm(UserChangeForm):
    role = forms.CharField(
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
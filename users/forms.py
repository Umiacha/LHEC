from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    UserChangeForm,
    UserCreationForm,
)
from django.contrib.auth.models import User
from .roles import UserRole, get_user_role
from .models import Employee


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
                'class': 'block w-full text-sm text-slate-700 file:mr-4 file:rounded-full file:border-0 file:bg-lab-950 file:px-4 file:py-2.5 file:font-semibold file:text-white hover:file:bg-lab-800',
                'accept': 'image/*',
            }),
            'bio': forms.Textarea(attrs={'class': INPUT_CLASSES, 'rows': 8}),
        }

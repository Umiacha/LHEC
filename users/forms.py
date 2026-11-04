from django.utils.translation import gettext_lazy as _
from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    UserChangeForm,
    UserCreationForm,
)
from django.contrib.auth.models import User
from .roles import UserRole, get_user_role
from .models import Employee, ScientificProfile


INPUT_CLASSES = 'form-control'


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label=_('Логин'),
        widget=forms.TextInput(
            attrs={
                'class': INPUT_CLASSES,
                'autocomplete': 'username',
                'autofocus': True,
            }
        ),
    )
    password = forms.CharField(
        label=_('Пароль'),
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

    scientific_profiles = forms.CharField(
        label=_('Научные профили'), required=False,
        help_text=_('Каждая ссылка — с новой строки. Чтобы удалить ссылку, удалите её строку.'),
        widget=forms.Textarea(attrs={'class': INPUT_CLASSES, 'rows': 4}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['scientific_profiles'] = '\n'.join(
                self.instance.scientific_profiles.values_list('url', flat=True)
            )

    def clean_scientific_profiles(self):
        field = forms.URLField(max_length=2000, assume_scheme='https')
        urls = []
        for line in self.cleaned_data['scientific_profiles'].splitlines():
            if line.strip():
                url = field.clean(line.strip())
                if url not in urls:
                    urls.append(url)
        return urls

    def save_profiles(self, employee):
        urls = self.cleaned_data['scientific_profiles']
        employee.scientific_profiles.exclude(url__in=urls).delete()
        for index, url in enumerate(urls):
            ScientificProfile.objects.update_or_create(
                employee=employee, url=url, defaults={'sort_order': index},
            )

    class Meta:
        model = Employee
        fields = ('last_name', 'first_name', 'mid_name', 'photo', 'bio')
        labels = {
            'last_name': _('Фамилия'), 'first_name': _('Имя'),
            'mid_name': _('Отчество'), 'photo': _('Фото'), 'bio': _('Описание'),
        }
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

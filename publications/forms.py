from django.utils.translation import gettext_lazy as _
from django import forms

from research.models import ResearchDirection
from users.models import Employee

from .models import Publication


class PublicationSearchForm(forms.Form):
    """Панель поиска и фильтров публикаций."""
    q = forms.CharField(
        label=_('Поиск'), required=False, max_length=500,
        widget=forms.TextInput(attrs={
            'type': 'search',
            'placeholder': _('Название, авторы, журнал или DOI'),
        }),
    )
    employee = forms.ModelChoiceField(
        label=_('Сотрудник лаборатории'), required=False,
        queryset=Employee.objects.none(), empty_label=_('Все сотрудники'),
    )
    year = forms.TypedChoiceField(
        label=_('Год'), required=False, coerce=int, empty_value=None,
    )
    direction = forms.ModelChoiceField(
        label=_('Научное направление'), required=False,
        queryset=ResearchDirection.objects.none(), empty_label=_('Все направления'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].label_from_instance = lambda obj: obj.localized_full_name
        self.fields['direction'].label_from_instance = lambda obj: obj.localized_name
        self.fields['employee'].queryset = Employee.objects.filter(
            is_published=True, publications__is_published=True,
        ).order_by('last_name', 'first_name', 'mid_name', 'pk').distinct()
        self.fields['direction'].queryset = ResearchDirection.objects.filter(
            is_published=True, publications__is_published=True,
        ).distinct()
        years = Publication.objects.filter(is_published=True, year__isnull=False).order_by(
            '-year',
        ).values_list('year', flat=True).distinct()
        self.fields['year'].choices = [('', _('Все годы')), *((year, year) for year in years)]
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


class PublicationImportForm(forms.Form):
    bibliography = forms.FileField(
        label='Файл BibTeX или RIS',
        widget=forms.ClearableFileInput(attrs={'accept': '.bib,.ris'}),
    )


class PublicationAdminForm(forms.ModelForm):
    duplicate_matches = ()

    confirm_duplicate = forms.BooleanField(
        label='Подтверждаю создание отдельной записи при найденном совпадении',
        required=False,
    )

    class Meta:
        model = Publication
        fields = '__all__'

    def clean(self):
        from .importers import ImportResult, find_duplicates

        data = super().clean()
        self.duplicate_matches = find_duplicates(
            ImportResult(data, '', ''), exclude_pk=self.instance.pk,
        )
        if self.duplicate_matches and not data.get('confirm_duplicate'):
            raise forms.ValidationError(
                'Найдены возможные дубли. Проверьте ссылки над формой и подтвердите '
                'сохранение отдельной записи, если это необходимо.'
            )
        return data

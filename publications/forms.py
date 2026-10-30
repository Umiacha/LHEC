from django import forms

from research.models import ResearchDirection
from users.models import Employee

from .models import Publication


class PublicationSearchForm(forms.Form):
    """Панель поиска и фильтров публикаций."""
    q = forms.CharField(
        label='Поиск', required=False, max_length=500,
        widget=forms.TextInput(attrs={
            'type': 'search',
            'placeholder': 'Название, авторы, журнал или DOI',
        }),
    )
    employee = forms.ModelChoiceField(
        label='Сотрудник лаборатории', required=False,
        queryset=Employee.objects.none(), empty_label='Все сотрудники',
    )
    year = forms.TypedChoiceField(
        label='Год', required=False, coerce=int, empty_value=None,
    )
    direction = forms.ModelChoiceField(
        label='Научное направление', required=False,
        queryset=ResearchDirection.objects.none(), empty_label='Все направления',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = Employee.objects.filter(
            is_published=True, publications__is_published=True,
        ).order_by('last_name', 'first_name', 'mid_name', 'pk').distinct()
        self.fields['direction'].queryset = ResearchDirection.objects.filter(
            is_published=True, publications__is_published=True,
        ).distinct()
        years = Publication.objects.filter(is_published=True).order_by(
            '-year',
        ).values_list('year', flat=True).distinct()
        self.fields['year'].choices = [('', 'Все годы'), *((year, year) for year in years)]
        for field in self.fields.values():
            field.widget.attrs['class'] = (
                'mt-2 block w-full min-w-0 rounded-xl border border-slate-300 '
                'bg-white px-4 py-3 text-base text-slate-700 '
                'focus:border-lab-800 focus:outline-none focus:ring-2 focus:ring-lab-800'
            )


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

from django import forms

from research.models import ResearchDirection
from users.models import Employee

from .models import Publication


class PublicationSearchForm(forms.Form):
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

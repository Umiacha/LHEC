from django.test import TestCase, override_settings
from django.urls import reverse

from users.models import AcademicDegree, Employee, EngineerPosition, SciencePosition
from publications.models import Publication


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class HomepagePublicationTests(TestCase):
    def test_selection_order_and_optional_content(self):
        def publication(title, **fields):
            return Publication.objects.create(
                title=title, authors_text='Авторы', year=2025, **fields,
            )

        second = publication('Вторая работа', is_published=True, is_on_homepage=True,
                             homepage_order=2, note='Значимый результат', doi='10.1234/example')
        first = publication('Первая работа', is_published=True, is_on_homepage=True,
                            homepage_order=1)
        publication('Скрытая работа', is_on_homepage=True)
        publication('Только избранная', is_published=True, is_featured=True)
        response = self.client.get(reverse('core:home'))
        self.assertEqual(list(response.context['homepage_publications']), [first, second])
        self.assertContains(response, reverse('publications:publication', args=[first.pk]))
        self.assertContains(response, 'Значимый результат')
        self.assertContains(response, 'https://doi.org/10.1234/example')
        self.assertNotContains(response, 'Скрытая работа')
        self.assertNotContains(response, 'Только избранная')
        content = response.content.decode()
        self.assertLess(content.index('id="science"'), content.index('id="publications"'))
        self.assertLess(content.index('id="publications"'), content.index('id="students"'))

    def test_empty_selection_hides_section(self):
        response = self.client.get(reverse('core:home'))
        self.assertNotContains(response, 'id="publications"')


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class HistoryStatisticsTests(TestCase):
    def test_counts_current_staff_and_degrees_among_scientists(self):
        def employee(**fields):
            return Employee.objects.create(last_name='Тест', first_name='Сотрудник', **fields)

        employee(science_position=SciencePosition.RESEARCH_FELLOW,
                 academic_degree=AcademicDegree.CANDIDATE_CHEMISTRY)
        employee(science_position=SciencePosition.SENIOR_RESEARCH_FELLOW,
                 academic_degree=AcademicDegree.CANDIDATE_PHYS_MATH, is_published=False)
        employee(science_position=SciencePosition.HEAD_OF_THE_LABORATORY,
                 engineer_position=EngineerPosition.TECHNICIAN,
                 academic_degree=AcademicDegree.DOCTOR_CHEMISTRY)
        employee(science_position=SciencePosition.JUNIOR_RESEARCH_FELLOW)
        employee(engineer_position=EngineerPosition.TECHNICIAN,
                 academic_degree=AcademicDegree.DOCTOR_PHYS_MATH)
        employee(is_current=False, science_position=SciencePosition.RESEARCH_FELLOW,
                 academic_degree=AcademicDegree.CANDIDATE_BIOLOGY)

        response = self.client.get(reverse('core:history'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['staff_statistics'], {
            'total': 5, 'scientific': 4, 'doctors': 1, 'candidates': 2,
        })
        self.assertContains(response, 'Сегодня коллектив лаборатории — 5 сотрудников, в том числе — 4 научных сотрудников, среди которых 1 доктора и 2 кандидатов наук.')

    def test_empty_staff_renders_zero_counts(self):
        response = self.client.get(reverse('core:history'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['staff_statistics'], {
            'total': 0, 'scientific': 0, 'doctors': 0, 'candidates': 0,
        })
        self.assertContains(response, 'Сегодня коллектив лаборатории — 0 сотрудников, в том числе — 0 научных сотрудников.')
        self.assertNotContains(response, 'среди которых')

    def test_hides_degree_group_with_zero_members(self):
        employee = Employee.objects.create(
            last_name='Тест', first_name='Сотрудник',
            science_position=SciencePosition.RESEARCH_FELLOW,
            academic_degree=AcademicDegree.DOCTOR_CHEMISTRY,
        )
        response = self.client.get(reverse('core:history'))
        self.assertContains(response, 'среди которых 1 доктора наук.')
        self.assertNotContains(response, 'кандидатов наук')

        employee.academic_degree = AcademicDegree.CANDIDATE_CHEMISTRY
        employee.save(update_fields=['academic_degree'])
        response = self.client.get(reverse('core:history'))
        self.assertContains(response, 'среди которых 1 кандидатов наук.')
        self.assertNotContains(response, 'доктора наук')

from django.forms.models import inlineformset_factory
from django.test import TestCase

from research.admin import ProjectParticipationFormSet
from research.models import ProjectParticipation, ResearchProject
from users.models import Employee


class ParticipationAdminValidationTests(TestCase):
    def test_mixed_staff_and_external_identity_has_readable_error(self):
        employee = Employee.objects.create(first_name='Иван', last_name='Иванов')
        formset_class = inlineformset_factory(
            ResearchProject, ProjectParticipation, formset=ProjectParticipationFormSet,
            fields=('employee', 'external_name', 'external_organization', 'role', 'sort_order'),
        )
        for external in ({'external_name': 'Пётр Петров'}, {'external_organization': 'МГУ'}):
            with self.subTest(external=external):
                data = {
                    'participations-TOTAL_FORMS': '1', 'participations-INITIAL_FORMS': '0',
                    'participations-0-employee': str(employee.pk),
                    'participations-0-role': 'executor', 'participations-0-sort_order': '0',
                    **{f'participations-0-{key}': value for key, value in external.items()},
                }
                formset = formset_class(data, instance=ResearchProject())
                self.assertFalse(formset.is_valid())
                errors = str(formset.forms[0].non_field_errors())
                self.assertIn('Если выбран сотрудник, оставьте ФИО и организацию внешнего участника пустыми.', errors)
                self.assertNotIn('research_project_participant_identity', errors)

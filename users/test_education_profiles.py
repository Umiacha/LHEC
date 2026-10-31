from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import EducationStatus, Employee, EngineerPosition, SciencePosition
from .roles import INTERNAL_MATERIALS_PERMISSION, UserRole, set_user_role


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class EducationProfileTests(TestCase):
    def person(self, **fields):
        return Employee.objects.create(last_name='Иванов', first_name='Иван', **fields)

    def test_optional_education_and_student_year_validation(self):
        for status, year in [('', None), (EducationStatus.STUDENT, None),
                             (EducationStatus.STUDENT, 4), (EducationStatus.POSTGRADUATE, None)]:
            Employee(last_name='Тест', first_name='Тест', education_status=status, study_year=year).full_clean()
        for status, year in [('', 1), (EducationStatus.POSTGRADUATE, 1),
                             (EducationStatus.STUDENT, 0), (EducationStatus.STUDENT, -1)]:
            with self.assertRaises(ValidationError):
                Employee(last_name='Тест', first_name='Тест', education_status=status, study_year=year).full_clean()

    def test_sections_and_combined_positions_without_duplicates(self):
        staff = self.person()
        student = self.person(education_status=EducationStatus.STUDENT, study_year=4)
        postgraduate = self.person(education_status=EducationStatus.POSTGRADUATE)
        employed_student = self.person(education_status=EducationStatus.STUDENT,
                                      engineer_position=EngineerPosition.TECHNICIAN)
        employed_postgraduate = self.person(education_status=EducationStatus.POSTGRADUATE,
                                           science_position=SciencePosition.JUNIOR_RESEARCH_FELLOW)
        hidden = self.person(education_status=EducationStatus.STUDENT, is_published=False)
        response = self.client.get(reverse('users:people'))
        sections = response.context['people_sections']
        self.assertCountEqual(sections[0][1], [staff, employed_student, employed_postgraduate])
        self.assertEqual(list(sections[1][1]), [postgraduate])
        self.assertEqual(list(sections[2][1]), [student])
        for person in [staff, student, postgraduate, employed_student, employed_postgraduate]:
            self.assertContains(response, reverse('users:employe_card', args=[person.pk]), count=1)
        self.assertNotContains(response, reverse('users:employe_card', args=[hidden.pk]))
        self.assertContains(response, 'Студент, 4 курс')
        self.assertContains(self.client.get(reverse('users:employe_card', args=[student.pk])),
                            'Студент, 4 курс')

    def test_learners_are_excluded_from_staff_statistics_unless_employed(self):
        self.person(education_status=EducationStatus.STUDENT)
        self.person(education_status=EducationStatus.POSTGRADUATE)
        self.person(education_status=EducationStatus.STUDENT, engineer_position=EngineerPosition.TECHNICIAN)
        self.person(education_status=EducationStatus.POSTGRADUATE,
                    science_position=SciencePosition.JUNIOR_RESEARCH_FELLOW)
        self.assertEqual(self.client.get(reverse('core:history')).context['staff_statistics'],
                         {'total': 2, 'scientific': 1, 'doctors': 0, 'candidates': 0})

    def test_student_account_gets_material_access_without_admin_access(self):
        user = User.objects.create_user(username='student', password='test-pass')
        self.person(education_status=EducationStatus.STUDENT, user=user)
        set_user_role(user, UserRole.EMPLOYEE)
        user = User.objects.get(pk=user.pk)
        self.assertTrue(user.has_perm(INTERNAL_MATERIALS_PERMISSION))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse('admin:index')),
                             reverse('admin:login') + '?next=' + reverse('admin:index'))
        set_user_role(user, UserRole.ADMINISTRATOR)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_owner_cannot_change_education_fields(self):
        user = User.objects.create_user(username='owner')
        person = self.person(user=user)
        self.client.force_login(user)
        response = self.client.post(reverse('users:edit_employe_card', args=[person.pk]), {
            'last_name': person.last_name, 'first_name': person.first_name, 'bio': '',
            'education_status': EducationStatus.STUDENT, 'study_year': 3,
        })
        self.assertEqual(response.status_code, 302)
        person.refresh_from_db()
        self.assertEqual(person.education_status, '')
        self.assertIsNone(person.study_year)

    def test_existing_employee_accounts_lose_only_admin_entry(self):
        from importlib import import_module
        from django.apps import apps
        from django.contrib.auth.models import Group
        from django.db import connection

        group = Group.objects.get(name='Сотрудники')
        employee = User.objects.create_user(username='existing', is_staff=True)
        administrator = User.objects.create_superuser(username='administrator')
        other = User.objects.create_user(username='other', is_staff=True)
        employee.groups.add(group)
        administrator.groups.add(group)
        migration = import_module('users.migrations.0006_employee_role_without_admin_access')
        from types import SimpleNamespace
        migration.remove_admin_access(apps, SimpleNamespace(connection=connection))
        employee.refresh_from_db()
        administrator.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(employee.is_staff)
        self.assertTrue(employee.has_perm(INTERNAL_MATERIALS_PERMISSION))
        self.assertTrue(administrator.is_staff)
        self.assertTrue(administrator.is_superuser)
        self.assertTrue(other.is_staff)

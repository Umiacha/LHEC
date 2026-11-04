from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from research.models import ResearchDirection
from users.models import EducationStatus, Employee, EngineerPosition, SciencePosition
from users.roles import INTERNAL_MATERIALS_PERMISSION, UserRole, set_user_role


class PeoplePageTests(TestCase):
    def test_list_shows_published_employee_with_link_and_fallback(self):
        employee = Employee.objects.create(
            last_name="Иванов",
            first_name="Иван",
            science_position=SciencePosition.RESEARCH_FELLOW,
        )
        Employee.objects.create(last_name="Скрытый", first_name="Сотрудник", is_published=False)

        response = self.client.get(reverse("users:people"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Иванов Иван")
        self.assertContains(response, employee.get_science_position_display())
        self.assertContains(response, reverse("users:employe_card", args=[employee.pk]))
        self.assertNotContains(response, "Скрытый")
        self.assertContains(response, "<svg", html=False)

    def test_card_of_unpublished_employee_is_not_public(self):
        employee = Employee.objects.create(last_name="Скрытый", first_name="Сотрудник", is_published=False)

        response = self.client.get(reverse("users:employe_card", args=[employee.pk]))

        self.assertEqual(response.status_code, 404)

    def test_card_shows_public_directions_for_member_and_leader_without_duplicates(self):
        employee = Employee.objects.create(last_name="Иванов", first_name="Иван")
        other = Employee.objects.create(last_name="Петров", first_name="Пётр")
        member = ResearchDirection.objects.create(name="Участие", slug="member", is_published=True, sort_order=1)
        member.employees.add(employee)
        leader = ResearchDirection.objects.create(name="Руководство", slug="leader", leader=employee, is_published=True)
        leader.employees.add(employee, other)
        hidden = ResearchDirection.objects.create(name="Скрытое направление", slug="hidden", leader=employee)
        hidden.employees.add(employee)
        ResearchDirection.objects.create(name="Чужое направление", slug="unrelated", is_published=True)

        response = self.client.get(reverse("users:employe_card", args=[employee.pk]))

        self.assertEqual(list(response.context["research_directions"]), [leader, member])
        self.assertContains(response, "Научные направления")
        for direction in (leader, member):
            self.assertContains(response, reverse("research:direction_detail", args=[direction.slug]), count=1)
        self.assertNotContains(response, "Скрытое направление")
        self.assertNotContains(response, "Чужое направление")

    def test_card_hides_directions_section_when_no_public_directions(self):
        employee = Employee.objects.create(last_name="Иванов", first_name="Иван")
        ResearchDirection.objects.create(name="Скрытое направление", slug="hidden", leader=employee)

        response = self.client.get(reverse("users:employe_card", args=[employee.pk]))

        self.assertNotContains(response, "Научные направления")


class EmployeeEditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="employee", password="test-password")
        self.employee = Employee.objects.create(
            last_name="Иванов", first_name="Иван", user=self.user,
        )
        self.edit_url = reverse("users:edit_employe_card", args=[self.employee.pk])

    def test_only_owner_sees_edit_link_and_can_open_form(self):
        card_url = reverse("users:employe_card", args=[self.employee.pk])
        self.assertNotContains(self.client.get(card_url), self.edit_url)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(card_url), self.edit_url)
        self.assertContains(self.client.get(self.edit_url), "Редактировать карточку")

    def test_guest_redirects_to_login_and_other_user_cannot_edit(self):
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("users:login"), response.url)

        other = User.objects.create_user(username="other", password="test-password")
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.edit_url).status_code, 404)
        self.assertEqual(self.client.post(self.edit_url, {}).status_code, 404)

    def test_post_updates_only_allowed_fields(self):
        self.client.force_login(self.user)
        other = User.objects.create_user(username="other", password="test-password")
        response = self.client.post(self.edit_url, {
            "last_name": "Петров", "first_name": "Пётр", "mid_name": "",
            "bio": "Новый текст", "user": other.pk, "is_published": "",
        })
        self.assertRedirects(response, reverse("users:employe_card", args=[self.employee.pk]))
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.last_name, "Петров")
        self.assertEqual(self.employee.bio, "Новый текст")
        self.assertEqual(self.employee.user, self.user)
        self.assertTrue(self.employee.is_published)

    def test_unsupported_method_is_rejected(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.put(self.edit_url, {}).status_code, 405)

    def test_owner_can_return_to_unpublished_card_after_editing(self):
        self.employee.is_published = False
        self.employee.save(update_fields=["is_published"])
        self.client.force_login(self.user)
        response = self.client.post(self.edit_url, {
            "last_name": "Иванов", "first_name": "Иван", "mid_name": "", "bio": "Текст",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Текст")

# Create your tests here.


class EmployeeAcademicProfileTests(TestCase):
    def test_current_filter_is_independent_of_publication(self):
        current = Employee.objects.create(
            last_name='Действующий', first_name='Сотрудник', is_published=False,
        )
        former = Employee.objects.create(
            last_name='Бывший', first_name='Сотрудник', is_current=False,
        )
        self.assertEqual(list(Employee.objects.current()), [current])
        self.assertEqual(list(Employee.objects.published()), [former])
        self.assertEqual(current.academic_degree, '')
        self.assertEqual(current.academic_title, '')

    def test_degree_and_title_are_visible_on_list_and_card(self):
        from .models import AcademicDegree, AcademicTitle

        employee = Employee.objects.create(
            last_name='Иванов', first_name='Иван',
            academic_degree=AcademicDegree.DOCTOR_CHEMISTRY,
            academic_title=AcademicTitle.PROFESSOR,
            is_current=False,
        )
        for url in (reverse('users:people'), reverse('users:employe_card', args=[employee.pk])):
            response = self.client.get(url)
            self.assertContains(response, 'д.х.н.')
            self.assertContains(response, 'проф.')
            self.assertNotContains(response, 'Действующий сотрудник')

    def test_profile_owner_cannot_change_employment_or_academic_fields(self):
        from .models import AcademicDegree, AcademicTitle

        user = User.objects.create_user(username='academic-owner')
        employee = Employee.objects.create(last_name='Иванов', first_name='Иван', user=user)
        self.client.force_login(user)
        response = self.client.post(reverse('users:edit_employe_card', args=[employee.pk]), {
            'last_name': 'Иванов', 'first_name': 'Иван', 'mid_name': '', 'bio': '',
            'academic_degree': AcademicDegree.DOCTOR_CHEMISTRY,
            'academic_title': AcademicTitle.PROFESSOR, 'is_current': '',
        })
        self.assertEqual(response.status_code, 302)
        employee.refresh_from_db()
        self.assertEqual(employee.academic_degree, '')
        self.assertEqual(employee.academic_title, '')
        self.assertTrue(employee.is_current)


    def test_degree_groups_include_all_disciplines(self):
        from .models import AcademicDegree

        for degree in AcademicDegree:
            Employee.objects.create(last_name=degree.value, first_name='Тест', academic_degree=degree)
        candidates = Employee.objects.filter(academic_degree__in=AcademicDegree.candidates())
        doctors = Employee.objects.filter(academic_degree__in=AcademicDegree.doctors())
        self.assertEqual(candidates.count(), 3)
        self.assertEqual(doctors.count(), 2)
        self.assertEqual(candidates.count() + doctors.count(), Employee.objects.count())


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

    def test_initial_employee_role_has_internal_permission_and_seed_is_idempotent(self):
        from importlib import import_module
        from types import SimpleNamespace
        from django.apps import apps
        from django.contrib.auth.models import Group
        from django.db import connection

        group = Group.objects.get(name='Сотрудники')
        self.assertTrue(group.permissions.filter(
            content_type__app_label='education', codename='view_internal_materials',
        ).exists())
        employee = User.objects.create_user(username='employee')
        set_user_role(employee, UserRole.EMPLOYEE)
        migration = import_module('users.migrations.0002_create_employee_role')
        migration.create_employee_role(apps, SimpleNamespace(connection=connection))
        self.assertEqual(Group.objects.filter(name='Сотрудники').count(), 1)
        self.assertTrue(employee.has_perm(INTERNAL_MATERIALS_PERMISSION))
        self.assertFalse(employee.is_staff)
        self.assertFalse(employee.is_superuser)


    def test_former_participants_appear_only_in_last_section(self):
        current_staff = self.person()
        current_student = self.person(education_status=EducationStatus.STUDENT)
        current_postgraduate = self.person(education_status=EducationStatus.POSTGRADUATE)
        former_staff = self.person(is_current=False, science_position=SciencePosition.RESEARCH_FELLOW)
        former_student = self.person(is_current=False, education_status=EducationStatus.STUDENT)
        former_postgraduate = self.person(is_current=False, education_status=EducationStatus.POSTGRADUATE)
        hidden = self.person(is_current=False, is_published=False)
        response = self.client.get(reverse('users:people'))
        sections = response.context['people_sections']
        self.assertEqual(list(sections[0][1]), [current_staff])
        self.assertEqual(list(sections[1][1]), [current_postgraduate])
        self.assertEqual(list(sections[2][1]), [current_student])
        title, former = sections[-1]
        self.assertEqual(title, 'Сотрудники и студенты лаборатории в прошлом')
        self.assertCountEqual(former, [former_staff, former_student, former_postgraduate])
        for person in [former_staff, former_student, former_postgraduate]:
            self.assertContains(response, reverse('users:employe_card', args=[person.pk]), count=1)
        self.assertNotContains(response, reverse('users:employe_card', args=[hidden.pk]))
        content = response.content.decode()
        self.assertGreater(content.index(title), content.index('>Студенты</h2>'))

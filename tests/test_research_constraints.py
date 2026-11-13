from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.forms import modelform_factory
from django.test import TestCase, TransactionTestCase

from research.models import ProjectParticipation, ResearchProject
from users.models import Employee


class ResearchCheckConstraintTests(TestCase):
    def setUp(self):
        self.project = ResearchProject.objects.create(
            name='Проект', slug='checks', start_year=2026, end_year=2028,
        )
        self.employee = Employee.objects.create(first_name='Иван', last_name='Иванов')

    def assert_database_rejects(self, write, constraint):
        with self.assertRaises(IntegrityError) as raised, transaction.atomic():
            write()
        # Verify that the intended constraint, rather than a foreign key or
        # an unrelated unique index, rejected the write.
        self.assertIn(constraint, str(raised.exception))

    def test_years_reject_create_update_bulk_create_bulk_update_and_raw_sql(self):
        for start, end in ((0, 2028), (2026, 2025), (2026, 0)):
            values = {'start_year': start, 'end_year': end}
            for operation in ('create', 'update', 'bulk_create', 'bulk_update', 'sql'):
                with self.subTest(years=values, operation=operation):
                    def write():
                        if operation == 'create':
                            ResearchProject.objects.create(name='Ошибка', slug='invalid', **values)
                        elif operation == 'bulk_create':
                            ResearchProject.objects.bulk_create([
                                ResearchProject(name='Ошибка', slug='invalid', **values),
                            ])
                        elif operation == 'bulk_update':
                            item = ResearchProject(pk=self.project.pk, **values)
                            ResearchProject.objects.bulk_update([item], ['start_year', 'end_year'])
                        elif operation == 'update':
                            ResearchProject.objects.filter(pk=self.project.pk).update(**values)
                        else:
                            with connection.cursor() as cursor:
                                cursor.execute(
                                    'UPDATE research_researchproject SET start_year=%s, end_year=%s WHERE id=%s',
                                    [start, end, self.project.pk],
                                )
                    self.assert_database_rejects(write, 'research_project_valid_years')
                    self.project.refresh_from_db()
                    self.assertEqual((self.project.start_year, self.project.end_year), (2026, 2028))

    def test_year_boundaries_and_forms_match_model(self):
        form_class = modelform_factory(ResearchProject, fields=('name', 'slug', 'start_year', 'end_year'))
        for start, end, valid in ((0, 1, False), (2026, 2025, False), (1, 1, True), (2026, 2026, True)):
            with self.subTest(start=start, end=end):
                data = {'name': 'Проект', 'slug': 'boundary', 'start_year': start, 'end_year': end}
                form = form_class(data=data)
                self.assertEqual(form.is_valid(), valid, form.errors)
                item = ResearchProject(**data)
                if valid:
                    item.full_clean()
                    item.save()
                    item.delete()
                else:
                    with self.assertRaises(ValidationError):
                        item.full_clean()

    def test_identity_rejects_all_write_paths(self):
        participant = ProjectParticipation.objects.create(project=self.project, employee=self.employee)
        for values in (
            {'employee_id': None, 'external_name': '', 'external_organization': ''},
            {'employee_id': None, 'external_name': '', 'external_organization': 'МГУ'},
            {'employee_id': self.employee.pk, 'external_name': 'Иван', 'external_organization': ''},
            {'employee_id': self.employee.pk, 'external_name': '', 'external_organization': 'МГУ'},
        ):
            for operation in ('create', 'update', 'bulk_create', 'bulk_update', 'sql'):
                with self.subTest(values=values, operation=operation):
                    def write():
                        if operation == 'create':
                            ProjectParticipation.objects.create(project=self.project, **values)
                        elif operation == 'bulk_create':
                            ProjectParticipation.objects.bulk_create([
                                ProjectParticipation(project=self.project, **values),
                            ])
                        elif operation == 'bulk_update':
                            item = ProjectParticipation(pk=participant.pk, project=self.project, **values)
                            ProjectParticipation.objects.bulk_update(
                                [item], ['employee', 'external_name', 'external_organization'],
                            )
                        elif operation == 'update':
                            ProjectParticipation.objects.filter(pk=participant.pk).update(**values)
                        else:
                            with connection.cursor() as cursor:
                                cursor.execute(
                                    'UPDATE research_projectparticipation '
                                    'SET employee_id=%s, external_name=%s, external_organization=%s WHERE id=%s',
                                    [values['employee_id'], values['external_name'],
                                     values['external_organization'], participant.pk],
                                )
                    self.assert_database_rejects(write, 'research_project_participant_identity')
                    participant.refresh_from_db()
                    self.assertEqual(participant.employee_id, self.employee.pk)

    def test_identity_forms_match_model_and_allow_external_without_organization(self):
        form_class = modelform_factory(
            ProjectParticipation, fields=('project', 'employee', 'external_name', 'external_organization'),
        )
        for employee, name, organization, valid in (
            ('', '', '', False), ('', '', 'МГУ', False), ('', ' \t\n ', '', False),
            (self.employee.pk, 'Иван', '', False), (self.employee.pk, '', 'МГУ', False),
            (self.employee.pk, '', '', True), ('', 'Иван', '', True), ('', 'Иван', 'МГУ', True),
        ):
            with self.subTest(employee=employee, name=name, organization=organization):
                form = form_class(data={
                    'project': self.project.pk, 'employee': employee,
                    'external_name': name, 'external_organization': organization,
                })
                self.assertEqual(form.is_valid(), valid, form.errors)
                item = ProjectParticipation(
                    project=self.project, employee_id=employee or None,
                    external_name=name, external_organization=organization,
                )
                if valid:
                    item.full_clean()
                    item.save()
                    item.delete()
                else:
                    with self.assertRaises(ValidationError):
                        item.full_clean()


class ConcurrentParticipationUpdateTests(TransactionTestCase):
    def test_concurrent_updates_allow_only_one_leader_or_duplicate_identity(self):
        project = ResearchProject.objects.create(name='Проект', slug='race', start_year=2026, end_year=2028)
        employee = Employee.objects.create(first_name='Иван', last_name='Иванов')
        for target in ('leader', 'employee', 'external'):
            with self.subTest(target=target):
                ProjectParticipation.objects.bulk_create([
                    ProjectParticipation(project=project, external_name='Первый'),
                    ProjectParticipation(project=project, external_name='Второй'),
                ])
                first, second = project.participations.order_by('pk')
                barrier = Barrier(2)

                def update(pk):
                    close_old_connections()
                    try:
                        values = {
                            'leader': {'role': 'leader'},
                            'employee': {'employee_id': employee.pk, 'external_name': ''},
                            'external': {'external_name': 'Один участник', 'external_organization': 'МГУ'},
                        }[target]
                        barrier.wait(timeout=10)
                        try:
                            with transaction.atomic():
                                ProjectParticipation.objects.filter(pk=pk).update(**values)
                            return True
                        except IntegrityError as error:
                            expected = {
                                'leader': 'research_project_one_leader',
                                'employee': 'research_project_unique_employee',
                                'external': 'research_project_unique_external',
                            }[target]
                            if expected not in str(error):
                                raise
                            return False
                    finally:
                        close_old_connections()

                with ThreadPoolExecutor(max_workers=2) as pool:
                    self.assertCountEqual(list(pool.map(update, (first.pk, second.pk))), [True, False])
                self.assertEqual(project.participations.count(), 2)
                project.participations.all().delete()

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, transaction
from django.test import TransactionTestCase

from research.models import ProjectParticipation, ResearchProject
from users.models import Employee


class ProjectParticipationUniquenessTests(TransactionTestCase):
    def setUp(self):
        self.project = ResearchProject.objects.create(name='Проект', slug='project', start_year=2026, end_year=2028)
        self.employee = Employee.objects.create(first_name='Иван', last_name='Иванов')

    def participant(self, **values):
        return ProjectParticipation(project=self.project, **values)

    def test_nullable_employee_and_generated_leader(self):
        leader = ProjectParticipation.objects.create(
            project=self.project, employee=self.employee, role='leader',
        )
        ProjectParticipation.objects.bulk_create([
            self.participant(external_name='Первый'),
            self.participant(external_name='Второй'),
        ])
        leader.refresh_from_db()
        self.assertEqual(leader.leader_project_id, self.project.pk)
        self.assertEqual(list(ProjectParticipation.objects.filter(
            role='executor',
        ).values_list('leader_project_id', flat=True)), [None, None])
        other_project = ResearchProject.objects.create(name='Другой', slug='other', start_year=2026, end_year=2028)
        ProjectParticipation.objects.create(
            project=other_project, employee=self.employee, role='leader',
        )

    def test_bulk_create_rejects_duplicates(self):
        for values in (
            [{'employee': self.employee}, {'employee': self.employee}],
            [{'external_name': 'Первый', 'role': 'leader'},
             {'external_name': 'Второй', 'role': 'leader'}],
        ):
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                ProjectParticipation.objects.bulk_create([
                    self.participant(**item) for item in values
                ])

    def test_update_and_bulk_update_reject_duplicates(self):
        ProjectParticipation.objects.bulk_create([
            self.participant(external_name='Первый'),
            self.participant(external_name='Второй'),
        ])
        first, second = self.project.participations.order_by('pk')
        for bulk in (False, True):
            for attribute, value in (('role', 'leader'), ('employee', self.employee)):
                with self.subTest(bulk=bulk, attribute=attribute):
                    # Empty external identity when assigning a staff employee.
                    if attribute == 'employee':
                        first.external_name = second.external_name = ''
                    for item in (first, second):
                        item.role = 'executor'
                        item.employee = None
                        setattr(item, attribute, value)
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        if bulk:
                            ProjectParticipation.objects.bulk_update(
                                [first, second], [attribute, 'external_name'],
                            )
                        else:
                            ProjectParticipation.objects.filter(pk__in=[first.pk, second.pk]).update(
                                **{attribute: value, 'external_name': '' if attribute == 'employee' else 'Внешний'},
                            )

    def test_leader_can_be_reassigned(self):
        first = ProjectParticipation.objects.create(
            project=self.project, employee=self.employee, role='leader',
        )
        second = ProjectParticipation.objects.create(project=self.project, external_name='Второй')
        ProjectParticipation.objects.filter(pk=first.pk).update(role='executor')
        ProjectParticipation.objects.filter(pk=second.pk).update(role='leader')
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(first.leader_project_id)
        self.assertEqual(second.leader_project_id, self.project.pk)

    def test_concurrent_inserts_allow_only_one(self):
        for identity in ('leader', 'employee', 'external'):
            with self.subTest(identity=identity):
                barrier = Barrier(2)

                def insert(number):
                    close_old_connections()
                    try:
                        barrier.wait(timeout=10)
                        if identity == 'employee':
                            values = {'employee_id': self.employee.pk}
                        elif identity == 'external':
                            values = {'external_name': 'Внешний', 'external_organization': 'МГУ'}
                        else:
                            values = {'external_name': f'Внешний {number}', 'role': 'leader'}
                        try:
                            with transaction.atomic():
                                ProjectParticipation.objects.create(project_id=self.project.pk, **values)
                            return True
                        except IntegrityError:
                            return False
                    finally:
                        close_old_connections()

                with ThreadPoolExecutor(max_workers=2) as pool:
                    self.assertCountEqual(list(pool.map(insert, range(2))), [True, False])
                self.assertEqual(self.project.participations.count(), 1)
                self.project.participations.all().delete()

    def test_external_identity_scope_and_staff_nulls(self):
        first = ProjectParticipation.objects.create(
            project=self.project, external_name='Иван Иванов', external_organization='МГУ',
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectParticipation.objects.create(
                project=self.project, external_name='Иван Иванов', external_organization='МГУ',
            )
        with self.assertRaises(ValidationError):
            self.participant(external_name='Иван Иванов', external_organization='МГУ').full_clean()
        ProjectParticipation.objects.create(
            project=self.project, external_name='Иван Иванов', external_organization='МИФИ',
        )
        ProjectParticipation.objects.create(
            project=self.project, external_name='Пётр Петров', external_organization='МГУ',
        )
        other = ResearchProject.objects.create(
            name='Другой', slug='other', start_year=2026, end_year=2028,
        )
        ProjectParticipation.objects.create(
            project=other, external_name='Иван Иванов', external_organization='МГУ',
        )
        second_employee = Employee.objects.create(first_name='Пётр', last_name='Петров')
        for employee in (self.employee, second_employee):
            staff = ProjectParticipation.objects.create(project=self.project, employee=employee)
            staff.refresh_from_db()
            self.assertIsNone(staff.external_identity_name)
            self.assertIsNone(staff.external_identity_organization)
        first.refresh_from_db()
        self.assertEqual(first.external_identity_name, first.external_name)
        self.assertEqual(first.external_identity_organization, first.external_organization)

    def test_external_bulk_create_and_updates_reject_duplicates(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectParticipation.objects.bulk_create([
                self.participant(external_name='Иван Иванов'),
                self.participant(external_name='Иван Иванов'),
            ])
        first = ProjectParticipation.objects.create(project=self.project, external_name='Иван Иванов')
        second = ProjectParticipation.objects.create(project=self.project, external_name='Пётр Петров')
        for bulk in (False, True):
            with self.subTest(bulk=bulk), self.assertRaises(IntegrityError), transaction.atomic():
                if bulk:
                    second.external_name = first.external_name
                    ProjectParticipation.objects.bulk_update([second], ['external_name'])
                else:
                    ProjectParticipation.objects.filter(pk=second.pk).update(external_name=first.external_name)

    def test_staff_to_external_recomputes_identity(self):
        ProjectParticipation.objects.create(project=self.project, external_name='Иван Иванов')
        staff = ProjectParticipation.objects.create(project=self.project, employee=self.employee)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectParticipation.objects.filter(pk=staff.pk).update(
                employee=None, external_name='Иван Иванов',
            )
        ProjectParticipation.objects.filter(pk=staff.pk).update(employee=None, external_name='Пётр Петров')
        staff.refresh_from_db()
        self.assertEqual(staff.external_identity_name, 'Пётр Петров')
        self.assertEqual(staff.external_identity_organization, '')
        ProjectParticipation.objects.filter(pk=staff.pk).update(employee=self.employee, external_name='')
        staff.refresh_from_db()
        self.assertIsNone(staff.external_identity_name)
        self.assertIsNone(staff.external_identity_organization)

    def test_identity_check_rejects_invalid_direct_writes(self):
        for values in ({}, {'external_organization': 'МГУ'},
                       {'employee': self.employee, 'external_name': 'Иван'},
                       {'employee': self.employee, 'external_organization': 'МГУ'}):
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                ProjectParticipation.objects.create(project=self.project, **values)

    def test_full_length_utf8mb4_external_identity(self):
        # Four-byte characters exercise the complete index, including its final character.
        values = {'external_name': '😀' * 255, 'external_organization': '🚀' * 500}
        first = ProjectParticipation.objects.create(project=self.project, **values)
        first.refresh_from_db()
        self.assertEqual(first.external_identity_name, values['external_name'])
        self.assertEqual(first.external_identity_organization, values['external_organization'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectParticipation.objects.create(project=self.project, **values)
        ProjectParticipation.objects.create(
            project=self.project, external_name=values['external_name'],
            external_organization='🚀' * 499 + '🌍',
        )

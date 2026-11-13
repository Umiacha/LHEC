from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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
        for employee in (False, True):
            with self.subTest(employee=employee):
                barrier = Barrier(2)

                def insert(number):
                    close_old_connections()
                    try:
                        barrier.wait(timeout=10)
                        values = {'employee_id': self.employee.pk} if employee else {
                            'external_name': f'Внешний {number}', 'role': 'leader',
                        }
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

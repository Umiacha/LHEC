from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class DiplomaMigrationTests(TransactionTestCase):
    def test_existing_work_and_supervisors_survive_move(self):
        executor = MigrationExecutor(connection)
        before = [('education', '0002_diploma'), ('research', '0007_alter_dissertation_file'),
                  ('users', '0006_employee_role_without_admin_access')]
        after = [('research', '0008_diploma')]
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            person = apps.get_model('users', 'Employee').objects.create(
                first_name='Иван', last_name='Иванов',
            )
            work = apps.get_model('education', 'Diploma').objects.create(
                title='Существующая ВКР', author_id=person.pk, year=2020,
                level='master', external_url='https://example.org/work',
                file='diplomas/2020/work.pdf', is_published=True,
            )
            work.supervisors.add(person)
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            apps = executor.loader.project_state(after).apps
            moved = apps.get_model('research', 'Diploma').objects.get(pk=work.pk)
            self.assertEqual(moved.title, 'Существующая ВКР')
            self.assertEqual(moved.author_id, person.pk)
            self.assertEqual(moved.file.name, 'diplomas/2020/work.pdf')
            self.assertEqual(list(moved.supervisors.values_list('pk', flat=True)), [person.pk])
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

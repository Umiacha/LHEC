"""Contract of the first MySQL installation, built from an empty test database."""
from django.contrib.auth.models import Group
from django.db import connection, migrations
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase

from education.models import StudentWorkTopic


class InitialMigrationTests(TestCase):
    def test_project_graph_has_no_legacy_schema_steps(self):
        loader = MigrationLoader(connection)
        expected = {
            ('core', '0001_initial'), ('core', '0002_auth_user_collations'),
            ('users', '0001_initial'), ('users', '0002_create_employee_role'),
            ('education', '0001_initial'), ('education', '0002_seed_student_work_topics'),
            ('research', '0001_initial'), ('publications', '0001_initial'),
        }
        actual = {key for key in loader.disk_migrations if key[0] in
                  {'core', 'users', 'education', 'research', 'publications'}}
        self.assertEqual(actual, expected)
        for key in expected:
            migration = loader.disk_migrations[key]
            self.assertFalse(migration.replaces)
            if key[1] == '0001_initial':
                self.assertTrue(migration.initial)
                self.assertFalse(any(isinstance(op, (migrations.RunPython, migrations.RunSQL))
                                     for op in migration.operations))

    def test_data_migrations_seed_topics_and_employee_permission(self):
        self.assertEqual(StudentWorkTopic.objects.filter(kind='diploma').count(), 18)
        self.assertEqual(StudentWorkTopic.objects.filter(kind='course').count(), 22)
        group = Group.objects.get(name='Сотрудники')
        self.assertTrue(group.permissions.filter(
            codename='view_internal_materials', content_type__app_label='education',
            content_type__model='teachingmaterial',
        ).exists())

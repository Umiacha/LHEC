"""Inspect the real schema built by the complete migration graph."""

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.db import IntegrityError, connection, models, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase

from research.models import ProjectParticipation, ResearchProject
from users.models import Employee


class MySQLMigrationSchemaTests(TransactionTestCase):
    def test_required_session_modes_preserve_existing_modes(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT @@SESSION.sql_mode, @@SESSION.default_storage_engine')
            original_mode, original_engine = cursor.fetchone()
            try:
                cursor.execute("SET SESSION sql_mode = 'ANSI_QUOTES'")
                cursor.execute(connection.settings_dict['OPTIONS']['init_command'])
                cursor.execute('SELECT @@SESSION.sql_mode')
                self.assertTrue({
                    'ANSI_QUOTES', 'STRICT_TRANS_TABLES', 'NO_ENGINE_SUBSTITUTION',
                } <= set(cursor.fetchone()[0].split(',')))
            finally:
                cursor.execute(
                    'SET SESSION sql_mode = %s, default_storage_engine = %s',
                    [original_mode, original_engine],
                )

    def test_complete_migration_schema_and_unicode_data(self):
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT @@character_set_database, @@collation_database, '
                '@@SESSION.default_storage_engine, @@SESSION.sql_mode, @@GLOBAL.sql_mode',
            )
            charset, collation, engine, session_mode, global_mode = cursor.fetchone()
            if settings.SETTINGS_MODULE == 'config.test_mysql_schema_settings':
                self.assertEqual((charset, collation, engine), ('latin1', 'latin1_swedish_ci', 'MyISAM'))
            else:
                self.assertEqual(engine, 'InnoDB')
            modes = set(session_mode.split(','))
            self.assertTrue({'STRICT_TRANS_TABLES', 'NO_ENGINE_SUBSTITUTION'} <= modes)
            self.assertTrue(set(global_mode.split(',')) - {''} <= modes)

            cursor.execute(
                'SELECT TABLE_NAME, ENGINE, TABLE_COLLATION, ROW_FORMAT '
                'FROM information_schema.TABLES '
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'",
            )
            tables = {name: (engine, collation, row_format) for name, engine, collation, row_format in cursor.fetchall()}
            all_models = [model for model in apps.get_models(include_auto_created=True)
                          if model._meta.managed and not model._meta.proxy]
            expected_tables = {model._meta.db_table for model in all_models} | {'django_migrations'}
            self.assertEqual(set(tables), expected_tables)
            for table, options in tables.items():
                with self.subTest(table=table):
                    self.assertEqual(options, ('InnoDB', 'utf8mb4_0900_ai_ci', 'Dynamic'))

            cursor.execute(
                'SELECT TABLE_NAME, COLUMN_NAME, CHARACTER_SET_NAME '
                'FROM information_schema.COLUMNS '
                'WHERE TABLE_SCHEMA = DATABASE() AND CHARACTER_SET_NAME IS NOT NULL',
            )
            for table, column, charset in cursor.fetchall():
                self.assertEqual(charset, 'utf8mb4', (table, column))

            for model in all_models:
                table = model._meta.db_table
                constraints = connection.introspection.get_constraints(cursor, table)
                for field in model._meta.local_fields:
                    with self.subTest(table=table, field=field.name):
                        if field.primary_key or field.unique:
                            self.assertTrue(any(
                                item['unique'] and item['columns'] == [field.column]
                                for item in constraints.values()
                            ))
                        elif field.db_index:
                            # InnoDB can reuse the leftmost prefix of a composed index.
                            self.assertTrue(any(
                                item['index'] and item['columns'][:1] == [field.column]
                                for item in constraints.values()
                            ))
                        if field.remote_field and field.db_constraint:
                            self.assertTrue(any(
                                item['columns'] == [field.column]
                                and item['foreign_key'] == (
                                    field.target_field.model._meta.db_table, field.target_field.column,
                                ) for item in constraints.values()
                            ))
                for fields in model._meta.unique_together:
                    columns = [model._meta.get_field(name).column for name in fields]
                    self.assertTrue(any(
                        item['unique'] and item['columns'] == columns for item in constraints.values()
                    ), (table, fields))
                for constraint in model._meta.constraints:
                    self.assertIn(constraint.name, constraints, table)
                    actual = constraints[constraint.name]
                    if isinstance(constraint, models.UniqueConstraint):
                        self.assertTrue(actual['unique'], (table, constraint.name))
                        self.assertEqual(actual['columns'], [model._meta.get_field(name).column for name in constraint.fields])
                    elif isinstance(constraint, models.CheckConstraint):
                        self.assertTrue(actual['check'], (table, constraint.name))
                for index in model._meta.indexes:
                    self.assertIn(index.name, constraints, table)
                    self.assertTrue(constraints[index.name]['index'])

        executor = MigrationExecutor(connection)
        self.assertEqual(executor.migration_plan(executor.loader.graph.leaf_nodes()), [])
        self.assertTrue(MigrationRecorder(connection).applied_migrations())

        # Exercise UTF-8 payloads, automatic M2M FKs, generated values and indexes.
        employee = Employee.objects.create(first_name='Иван 😀', last_name='Иванов')
        project = ResearchProject.objects.create(
            name='Проект 🚀', slug='schema-check', start_year=2026, end_year=2028,
        )
        participation = ProjectParticipation.objects.create(project=project, employee=employee, role='leader')
        participation.refresh_from_db()
        self.assertEqual(participation.leader_project_id, project.pk)
        self.assertIsNone(participation.external_identity_name)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectParticipation.objects.create(project=project, external_name='Внешний 😀', role='leader')
        external = ProjectParticipation.objects.create(
            project=project, external_name='Внешний 😀', external_organization='Институт 🚀',
        )
        external.refresh_from_db()
        self.assertEqual(external.external_identity_name, 'Внешний 😀')
        self.assertEqual(external.external_identity_organization, 'Институт 🚀')
        employee.refresh_from_db()
        project.refresh_from_db()
        self.assertEqual(employee.first_name, 'Иван 😀')
        self.assertEqual(project.name, 'Проект 🚀')
        user = User.objects.create_user(username='schema-user')
        group = Group.objects.create(name='Группа 😀')
        user.groups.add(group)
        self.assertEqual(user.groups.get().name, 'Группа 😀')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.groups.through.objects.create(user_id=user.pk, group_id=group.pk + 1_000_000)

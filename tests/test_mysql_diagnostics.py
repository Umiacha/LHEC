from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError, connection
from django.test import SimpleTestCase, TestCase

from core.management.commands.check_mysql import REQUIRED_COLLATIONS, inspect_configuration


class DiagnosticPolicyTests(SimpleTestCase):
    def setUp(self):
        self.variables = {
            'sql_mode': 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION',
            'transaction_isolation': 'READ-COMMITTED',
            'character_set_client': 'utf8mb4', 'character_set_connection': 'utf8mb4',
            'character_set_results': 'utf8mb4', 'collation_connection': 'utf8mb4_0900_ai_ci',
            'character_set_database': 'utf8mb4', 'collation_database': 'utf8mb4_0900_ai_ci',
            'default_storage_engine': 'InnoDB', 'innodb_page_size': '16384',
            'innodb_default_row_format': 'dynamic',
        }

    def inspect(self, version='8.0.46', collations=REQUIRED_COLLATIONS):
        return inspect_configuration(version, '', self.variables, {'innodb': 'DEFAULT'}, collations)

    def test_compatible_older_version_only_warns(self):
        errors, warnings = self.inspect('8.0.17')
        self.assertEqual(errors, [])
        self.assertTrue(warnings)

    def test_incompatible_versions(self):
        for version in ('8.0.15', '5.7.44', '10.11.0-MariaDB'):
            with self.subTest(version=version):
                self.assertTrue(self.inspect(version)[0])

    def test_index_budget_and_missing_collation(self):
        self.variables['innodb_page_size'] = '8192'
        errors, _ = self.inspect(collations=set())
        self.assertTrue(any('1536' in error and '3028' in error for error in errors))
        self.assertTrue(any('collation' in error for error in errors))

    def test_session_policy_errors(self):
        for key, value in (('sql_mode', ''), ('transaction_isolation', 'REPEATABLE-READ'),
                           ('character_set_client', 'latin1'), ('default_storage_engine', 'MyISAM'),
                           ('read_only', 'ON')):
            with self.subTest(key=key), patch.dict(self.variables, {key: value}):
                self.assertTrue(self.inspect()[0])

    def test_database_defaults_only_warn(self):
        self.variables.update(character_set_database='latin1', collation_database='latin1_swedish_ci')
        errors, warnings = self.inspect()
        self.assertEqual(errors, [])
        self.assertTrue(warnings)

    def test_connection_failure_hides_driver_message(self):
        output = StringIO()
        with patch('core.management.commands.check_mysql.connection') as mocked:
            mocked.vendor = 'mysql'
            mocked.cursor.side_effect = OperationalError(1045, 'password=secret://host')
            with self.assertRaises(CommandError) as result:
                call_command('check_mysql', stdout=output)
        self.assertIn('1045', str(result.exception))
        self.assertNotIn('secret', str(result.exception))
        self.assertNotIn('secret', output.getvalue())


class LiveDiagnosticTests(TestCase):
    def test_real_server_and_read_only_queries(self):
        statements = []
        def capture(execute, sql, params, many, context):
            statements.append(sql)
            return execute(sql, params, many, context)
        output = StringIO()
        with connection.execute_wrapper(capture):
            call_command('check_mysql', verbosity=2, stdout=output)
        self.assertIn('обязательные проверки пройдены', output.getvalue())
        self.assertIn('innodb_page_size:', output.getvalue())
        self.assertTrue(statements)
        self.assertTrue(all(sql.startswith(('SELECT', 'SHOW')) for sql in statements))

"""Safety checks for dev tooling; no real database or service mutations."""
import os
import unittest
from unittest.mock import MagicMock, patch

from scripts import dev_db


class DevDatabaseTests(unittest.TestCase):
    def options(self, url):
        with patch.dict(os.environ, DATABASE_URL=url), patch.object(dev_db, 'load_dotenv'):
            return dev_db.connection_options()

    def test_local_target(self):
        options = self.options('mysql://lhec_dev:secret@127.0.0.1:3306/lhecdev')
        self.assertEqual(options['host'], '127.0.0.1')
        self.assertEqual(options['passwd'], 'secret')
        options = self.options('mysql://lhec_dev:secret@%2Frun%2Fmysqld%2Fmysqld.sock/lhecdev')
        self.assertEqual(options['unix_socket'], str(dev_db.SOCKET))

    def test_reject_arbitrary_targets_and_url_options(self):
        for url in (
            '', 'postgresql://lhec_dev@localhost/lhecdev',
            'mysql://lhec_dev@remote/lhecdev', 'mysql://root@localhost/lhecdev',
            'mysql://lhec_dev@localhost/production', 'mysql://lhec_dev@localhost:3307/lhecdev',
            'mysql://lhec_dev@localhost/lhecdev?unix_socket=/tmp/other.sock',
            'mysql://lhec_dev@%2Ftmp%2Fother.sock/lhecdev',
        ):
            with self.subTest(url=url), self.assertRaises(SystemExit):
                self.options(url)

    def connection(self, identity=('lhecdev', 'lhec_dev@localhost', '8.0.46')):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = identity
        return connection, cursor

    def test_prepare_only_creates_fixed_database(self):
        connection, cursor = self.connection()
        with patch.object(dev_db, 'connect', return_value=connection):
            dev_db.prepare({})
        cursor.execute.assert_called_once_with(dev_db.DDL)
        connection.close.assert_called_once()

    def test_reset_rejects_wrong_actual_identity(self):
        for identity in (('production', 'lhec_dev@localhost', '8.0.46'),
                         ('lhecdev', 'root@localhost', '8.0.46'),
                         ('lhecdev', 'lhec_dev@localhost', '10.11-MariaDB')):
            connection, cursor = self.connection(identity)
            with patch.object(dev_db, 'connect', return_value=connection), patch('builtins.input') as prompt:
                with self.assertRaises(SystemExit):
                    dev_db.reset({})
            prompt.assert_not_called()
            self.assertEqual(cursor.execute.call_count, 1)
            connection.close.assert_called_once()

    def test_cancel_and_eof_never_drop(self):
        for response in ('wrong', EOFError()):
            connection, cursor = self.connection()
            kwargs = {'side_effect': response} if isinstance(response, Exception) else {'return_value': response}
            with patch.object(dev_db, 'connect', return_value=connection), patch('builtins.input', **kwargs):
                with self.assertRaises(SystemExit):
                    dev_db.reset({})
            self.assertEqual(cursor.execute.call_count, 1)

    def test_reset_pins_migration_target_and_preserves_password(self):
        connection, cursor = self.connection()
        options = self.options('mysql://lhec_dev:p%40ss%2Fword@127.0.0.1/lhecdev')
        with patch.object(dev_db, 'connect', return_value=connection), \
                patch('builtins.input', return_value='lhecdev'), \
                patch.object(dev_db.subprocess, 'run') as run, \
                patch.dict(os.environ, DATABASE_URL='mysql://root@remote/production'):
            dev_db.reset(options)
        self.assertEqual([call.args[0] for call in cursor.execute.call_args_list][1:],
                         ['DROP DATABASE `lhecdev`', dev_db.DDL])
        target = run.call_args.kwargs['env']['DATABASE_URL']
        self.assertEqual(self.options(target), options)
        self.assertIn('migrate', run.call_args.args[0])

    def test_service_stop_requires_confirmation(self):
        with patch.object(dev_db.Path, 'is_dir', return_value=True), \
                patch('builtins.input', return_value='no'), patch.object(dev_db.subprocess, 'run') as run:
            with self.assertRaises(SystemExit):
                dev_db.service('stop')
        run.assert_not_called()

    def test_service_start_only_explicit_systemctl(self):
        with patch.object(dev_db.Path, 'is_dir', return_value=True), patch.object(dev_db.subprocess, 'run') as run:
            dev_db.service('start')
        run.assert_called_once_with(['sudo', 'systemctl', 'start', 'mysql.service'], check=True)

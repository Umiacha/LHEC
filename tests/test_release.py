"""Packaging integration checks; no database, network or external builders required."""
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('build_release', Path(__file__).resolve().parents[1] / 'scripts/build_release.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_archive_contract_and_dirty_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = {
                **{name: 'placeholder' for name in release.FILES},
                'README.md': 'Repository documentation; must not ship',
                '.gitignore': '.env\ndist/\n',
                'config/settings.py': '', 'config/wsgi.py': '',
                'core/static/core/css/main.css': 'old css',
                'core/templates/core/home.html': 'template',
                'locale/en/LC_MESSAGES/django.po': 'catalog',
                'locale/en/LC_MESSAGES/django.mo': 'old translation',
                'publications/test_data/article.ris': 'fixture',
                'core/tests.py': 'test', 'config/test_security.py': 'test',
                'scripts/dev_db.py': 'dev tool', 'media/upload.jpg': 'local upload',
                'pyproject.toml': 'build configuration',
                'Makefile': (release.ROOT / 'Makefile').read_text(),
                'scripts/build_release.py': (release.ROOT / 'scripts/build_release.py').read_text(),
            }
            for app in release.APPS[1:]:
                files[f'{app}/migrations/__init__.py'] = ''
                files[f'{app}/migrations/0001_initial.py'] = 'migration'
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            def git(*args):
                return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True, text=True)
            git('init')
            git('add', '.')
            git('-c', 'user.name=Release Test', '-c', 'user.email=test@example.org', 'commit', '-m', 'fixture')
            (root / '.env').write_text('SECRET=must-not-ship')
            tools = root / 'fake-tools'
            tools.mkdir()
            # Ignore tool doubles; they model only external builders, not Make or packaging.
            with (root / '.git/info/exclude').open('a') as excluded:
                excluded.write('\nfake-tools/\n')
            tool_script = """#!INTERPRETER
import os
from pathlib import Path
import sys
assert not Path('.env').exists()
assert 'DJANGO_SETTINGS_MODULE' not in os.environ
args = sys.argv[1:]
name = Path(sys.argv[0]).name
with open(os.environ['RELEASE_TEST_LOG'], 'a') as log:
    log.write(name + ' ' + ' '.join(args) + '\\n')
if os.environ.get('RELEASE_TEST_FAIL') == name:
    sys.exit(1)
if name == 'uv' and args[0] == 'export':
    Path('requirements.txt').write_text('locked dependencies')
if name == 'npm' and args == ['run', 'css:build']:
    Path('core/static/core/css/main.css').write_text('built css')
if name == 'uv' and args[0] == 'run':
    catalog = Path('locale/en/LC_MESSAGES/django.mo')
    assert not catalog.exists()
    catalog.write_text('compiled translation')
""".replace('INTERPRETER', sys.executable)
            for name in ('uv', 'npm', 'msgfmt'):
                executable = tools / name
                executable.write_text(tool_script)
                executable.chmod(0o755)
            log = tools / 'commands.log'
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                       RELEASE_TEST_LOG=str(log), DJANGO_SETTINGS_MODULE='must_be_removed')
            def make(**overrides):
                return subprocess.run(['make', '-j2', 'release'], cwd=root,
                                      env=dict(env, **overrides), capture_output=True, text=True)
            result = make()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(log.read_text().splitlines(), [
                'uv sync --locked --no-dev',
                'uv export --locked --no-dev --no-emit-project --output-file requirements.txt',
                'npm ci', 'npm run css:build',
                'uv run --no-sync django-admin compilemessages --ignore=.venv --ignore=node_modules',
            ])
            self.assertEqual((root / 'core/static/core/css/main.css').read_text(), 'old css')
            self.assertEqual((root / 'locale/en/LC_MESSAGES/django.mo').read_text(), 'old translation')
            artifact, = (root / 'dist').glob('*.tar.gz')
            expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
            self.assertEqual(Path(str(artifact) + '.sha256').read_text().split()[0], expected)
            with tarfile.open(artifact) as archive:
                prefix = artifact.name.removesuffix('.tar.gz') + '/'
                names = {member.name.removeprefix(prefix) for member in archive if member.isfile()}
                self.assertEqual(names, {name for name in files if release.allowed(Path(name))} | {'RELEASE.json'})
                for excluded in ('README.md', '.env', 'core/tests.py', 'config/test_security.py', 'media/upload.jpg', 'scripts/dev_db.py', 'pyproject.toml'):
                    self.assertNotIn(excluded, names)
                self.assertEqual(archive.extractfile(prefix + 'core/static/core/css/main.css').read(), b'built css')
                metadata = json.load(archive.extractfile(prefix + 'RELEASE.json'))
                self.assertEqual(metadata['commit'], git('rev-parse', 'HEAD').stdout.strip())
                self.assertEqual(set(metadata['files']), names - {'RELEASE.json'})
            # A failed preparation must never publish an archive.
            shutil.rmtree(root / 'dist')
            result = make(RELEASE_TEST_FAIL='npm')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / 'dist').exists())
            (root / 'config/settings.py').write_text('uncommitted change')
            result = make()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('не чистое', result.stderr)


if __name__ == '__main__':
    unittest.main()

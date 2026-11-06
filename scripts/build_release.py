#!/usr/bin/env python3
"""Validate and package resources prepared by make release."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import tarfile
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parent.parent
APPS = ('config', 'core', 'education', 'publications', 'research', 'users')
FILES = ('manage.py', 'requirements.txt', 'Makefile.prod', '.env.example')
RESOURCES = {'templates', 'static'}


def allowed(path):
    parts = path.parts
    if len(parts) == 1:
        return parts[0] in FILES
    if any(p.startswith('.') or p in {'__pycache__', 'tests', 'test_data', 'node_modules'}
           or p == 'tests.py' or p.startswith('test_') or p.endswith('_test.py')
           for p in parts):
        return False
    if parts[0] == 'locale':
        return path.suffix in {'.po', '.mo'}
    if parts[0] not in APPS:
        return False
    return path.suffix == '.py' or bool(RESOURCES.intersection(parts[1:-1]))


def build(source, output, commit, timestamp):
    source = Path(source).resolve()
    output = Path(output).resolve()
    with (source / 'pyproject.toml').open('rb') as project_file:
        version = tomllib.load(project_file).get('project', {}).get('version')
    if not isinstance(version, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version):
        raise RuntimeError('project.version в pyproject.toml должна иметь формат X.Y.Z (например, 0.1.0)')
    name = f'lhec-{version}-{commit}'
    with tempfile.TemporaryDirectory(prefix='lhec-package-') as temporary:
        work = Path(temporary)
        release = work / name
        release.mkdir()
        selected = []
        for path in sorted(source.rglob('*')):
            relative = path.relative_to(source)
            if path.is_file() and allowed(relative):
                if path.is_symlink():
                    raise RuntimeError(f'Символическая ссылка в поставке запрещена: {relative}')
                destination = release / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
                selected.append(relative.as_posix())
        required = list(FILES) + ['config/settings.py', 'config/wsgi.py',
                                  'core/static/core/css/main.css', 'locale/en/LC_MESSAGES/django.mo']
        for app in APPS[1:]:
            required.append(f'{app}/migrations/__init__.py')
        for path in required:
            if not (release / path).is_file():
                raise RuntimeError(f'В поставке отсутствует обязательный файл: {path}')
        # Every tracked runtime resource and migration must survive filtering.
        for path in source.rglob('*'):
            relative = path.relative_to(source)
            if (path.is_file() and relative.parts[0] in APPS
                    and {'migrations', 'templates', 'static'}.intersection(relative.parts[1:-1])
                    and relative.suffix not in {'.pyc', '.pyo'}
                    and relative.as_posix() not in selected):
                raise RuntimeError(f'Ресурс ошибочно исключён: {relative}')
        metadata = {'version': version, 'commit': commit, 'commit_timestamp': timestamp, 'files': selected}
        (release / 'RELEASE.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
        artifact = work / f'{name}.tar.gz'
        with tarfile.open(artifact, 'w:gz') as archive:
            archive.add(release, arcname=name)
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        output.mkdir(exist_ok=True)
        shutil.copyfile(artifact, output / artifact.name)
        (output / f'{artifact.name}.sha256').write_text(f'{digest}  {artifact.name}\n')
    print(f'Готово: {output / artifact.name}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--timestamp', required=True, type=int)
    arguments = parser.parse_args()
    if len(arguments.commit) not in (40, 64) or any(c not in '0123456789abcdef' for c in arguments.commit):
        parser.error('--commit must be a full Git commit hash')
    try:
        build(arguments.source, arguments.output, arguments.commit, arguments.timestamp)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error

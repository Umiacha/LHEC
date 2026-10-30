"""Single-publication BibTeX/RIS import. Parsing never writes to the database.

Use parse_publication(upload) for a Django uploaded file, or pass text/bytes and
format='bibtex'/'ris'. Inspect errors before saving; warnings require review.
"""

from dataclasses import dataclass, field
import re
import unicodedata
from urllib.parse import unquote, urlsplit

from bibtexparser.bparser import BibTexParser
from pylatexenc.latex2text import LatexNodes2Text
from pyparsing import ParseBaseException
import rispy

from django.core.exceptions import ValidationError

from .models import Publication

MAX_FILE_SIZE = 2 * 1024 * 1024


class PublicationImportError(ValueError):
    """The input cannot be read as exactly one bibliographic record."""


@dataclass
class ImportResult:
    data: dict
    source_format: str
    source_type: str
    warnings: list[str] = field(default_factory=list)
    errors: dict[str, list[str]] = field(default_factory=dict)
    unmapped_fields: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DuplicateMatch:
    publication: Publication
    reason: str  # doi or title_year


def normalize_doi(value):
    value = value.strip()
    value = re.sub(r'^doi\s*:\s*', '', value, flags=re.I)
    if re.match(r'^https?://(?:dx\.)?doi\.org/', value, re.I):
        value = urlsplit(value).path.lstrip('/')
    return unquote(value).strip().casefold()


def _title_key(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    return ''.join(character for character in value if character.isalnum())


def find_duplicates(result, *, queryset=None, exclude_pk=None):
    """Return review candidates, including unpublished records; never update them."""
    queryset = Publication.objects.all() if queryset is None else queryset
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    doi = normalize_doi(result.data.get('doi', ''))
    title = _title_key(result.data.get('title', ''))
    year = result.data.get('year')
    matches = []
    for publication in queryset.iterator():
        if doi and normalize_doi(publication.doi) == doi:
            matches.append(DuplicateMatch(publication, 'doi'))
        elif (not doi and title and year == publication.year
              and _title_key(publication.title) == title):
            matches.append(DuplicateMatch(publication, 'title_year'))
    return matches


def _read(source):
    if hasattr(source, 'read'):
        source = source.read(MAX_FILE_SIZE + 1)
    if isinstance(source, bytes):
        if len(source) > MAX_FILE_SIZE:
            raise PublicationImportError('Размер файла превышает 2 МБ.')
        try:
            source = source.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise PublicationImportError('Сохраните файл в кодировке UTF-8.') from exc
    if not isinstance(source, str):
        raise PublicationImportError('Ожидается файл, текст или байты.')
    if len(source.encode('utf-8')) > MAX_FILE_SIZE:
        raise PublicationImportError('Размер файла превышает 2 МБ.')
    source = source.lstrip('\ufeff').strip()
    if not source:
        raise PublicationImportError('Файл пуст.')
    return source.replace('\r\n', '\n').replace('\r', '\n')


def _bibtex(text):
    parser = BibTexParser(common_strings=True, ignore_nonstandard_types=False)
    try:
        database = parser.parse(text)
    except (ParseBaseException, ValueError, KeyError) as exc:
        raise PublicationImportError('Некорректный BibTeX: проверьте структуру записи и строки @string.') from exc
    # bibtexparser accepts broken entries as implicit comments. Do not silently
    # import the first record when another malformed record follows it.
    if any(re.search(r'@\w+\s*[{(]', comment) for comment in database.comments):
        raise PublicationImportError('В BibTeX найдена повреждённая запись.')
    if len(database.entries) != 1:
        raise PublicationImportError('Файл должен содержать ровно одну публикацию.')
    record = database.entries[0].copy()
    kind = record.pop('ENTRYTYPE')
    record.pop('ID', None)
    raw_authors = record.get('author', '')
    names = _bibtex_names(raw_authors)
    latex = LatexNodes2Text()
    def clean(value):
        return ' '.join(latex.latex_to_text(value).split())
    record = {key: clean(value) for key, value in record.items()}
    record['author'] = '; '.join(clean(_name(name)) for name in names)
    return kind, record


def _bibtex_names(value):
    # Braced corporate authors may themselves contain the word "and".
    names, start, depth = [], 0, 0
    for match in re.finditer(r'\\.|[{}]|\s+and\s+', value):
        token = match.group()
        if token == '{':
            depth += 1
        elif token == '}':
            depth -= 1
        elif token.strip() == 'and' and depth == 0:
            names.append(value[start:match.start()].strip())
            start = match.end()
    if value[start:].strip():
        names.append(value[start:].strip())
    return names


def _name(value):
    if value.startswith('{') and value.endswith('}'):
        return value
    parts = [part.strip() for part in value.split(',')]
    if len(parts) == 2:
        return f'{parts[1]} {parts[0]}'
    if len(parts) == 3:
        return f'{parts[2]} {parts[0]}, {parts[1]}'
    return value.strip()


def _ris(text):
    # rispy tolerates an unfinished last record and text outside records.
    # Validate boundaries first so that no publication is silently discarded.
    active = False
    previous_tag = False
    tags = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.match(r'^([A-Z][A-Z0-9])  -(?: ?(.*))?$', line)
        if not match:
            if not active or not previous_tag or re.match(r'^[A-Z0-9]{2}\s+-', line):
                raise PublicationImportError('Некорректная строка RIS.')
            continue
        tag, value = match.groups()
        tags.add(tag)
        if tag == 'TY':
            if active or not value:
                raise PublicationImportError('Некорректное начало записи RIS.')
            active = True
        elif not active:
            raise PublicationImportError('Поле RIS находится вне записи TY — ER.')
        if tag == 'ER':
            active = False
        previous_tag = tag not in {'TY', 'ER'}
    if active:
        raise PublicationImportError('Запись RIS не завершена тегом ER.')
    records = rispy.loads(text, mapping={tag: tag for tag in tags | {'UK'}},
                          list_tags=['AU', 'A1'], delimiter_tags_mapping={})
    if len(records) != 1:
        raise PublicationImportError('Файл должен содержать ровно одну публикацию.')
    record = records[0]
    kind = record.pop('TY')
    authors = record.pop('AU', None) or record.pop('A1', [])
    record.pop('A1', None)
    record['author'] = '; '.join(_name(name) for name in authors)
    return kind, record


def parse_publication(source, *, format=None):
    """Read one UTF-8 record; return model field values, warnings and errors.

    A malformed/multiple-record file raises PublicationImportError. Missing or
    invalid model values are reported in result.errors so a form can fix them.
    Unknown and unsupported source fields are retained in unmapped_fields.
    """
    text = _read(source)
    source_format = (format or ('ris' if text.startswith('TY  -') else 'bibtex')).lower().lstrip('.')
    if source_format == 'bib':
        source_format = 'bibtex'
    if source_format not in {'bibtex', 'ris'}:
        raise PublicationImportError('Поддерживаются только BibTeX и RIS.')
    bib = source_format == 'bibtex'
    kind, record = _bibtex(text) if bib else _ris(text)
    types = ({'article': 'article', 'inproceedings': 'conference', 'conference': 'conference',
              'proceedings': 'conference', 'book': 'book', 'inbook': 'chapter',
              'incollection': 'chapter', 'misc': 'other'} if bib else
             {'JOUR': 'article', 'EJOUR': 'article', 'CONF': 'conference', 'CPAPER': 'conference',
              'BOOK': 'book', 'CHAP': 'chapter', 'GEN': 'other'})
    result = ImportResult({'kind': types.get(kind, 'other'), 'is_published': False}, source_format, kind)
    if kind not in types:
        result.warnings.append(f'Неизвестный тип «{kind}»: выбран тип «Другое».')

    def take(*keys):
        values = [record.pop(key, '') for key in keys]
        return next((' '.join(value.split()) for value in values if value and value.strip()), '')

    mapping = ({'title': ('title',), 'year': ('year', 'date'), 'authors_text': ('author',),
                'venue': (('journal', 'journaltitle', 'booktitle') if result.data['kind'] == 'article'
                          else ('booktitle', 'journal', 'journaltitle')),
                'volume': ('volume',), 'issue': ('number', 'issue'), 'pages': ('pages', 'eid'),
                'doi': ('doi',), 'external_url': ('url',), 'abstract': ('abstract',)} if bib else
               {'title': ('TI', 'T1'), 'year': ('PY', 'Y1', 'DA'), 'authors_text': ('author',),
                'venue': ('JO', 'JF', 'T2', 'JA'), 'volume': ('VL',), 'issue': ('IS',),
                'pages': ('SP',), 'doi': ('DO',), 'external_url': ('UR',), 'abstract': ('AB', 'N2')})
    for target, keys in mapping.items():
        result.data[target] = take(*keys)
    if not bib:
        end = take('EP')
        if end and result.data['pages'] and end != result.data['pages']:
            result.data['pages'] += '–' + end
    result.data['pages'] = result.data['pages'].replace('--', '–')
    year = result.data['year']
    result.data['year'] = int(year[:4]) if re.fullmatch(r'\d{4}(?:[-/].*)?', year) else None
    if year and result.data['year'] is None:
        result.warnings.append(f'Не удалось распознать год «{year}».')
    result.data['doi'] = normalize_doi(result.data['doi'])
    if result.data['doi'] and not re.fullmatch(r'10\.\d{4,9}/\S+', result.data['doi']):
        result.errors['doi'] = ['Некорректный DOI.']
    url = result.data['external_url']
    try:
        hostname = urlsplit(url).hostname
    except ValueError:
        hostname = None  # URLField validation below reports the malformed URL.
    if hostname in {'istina.msu.ru', 'istina.msu.su'}:
        result.data['istina_url'] = result.data.pop('external_url')
    result.unmapped_fields = record
    if record:
        result.warnings.append('Не перенесены поля: ' + ', '.join(sorted(record)) + '.')
    # Field validation includes required values, URL validity and model lengths;
    # it deliberately excludes relations and performs no database writes.
    for name, value in result.data.items():
        model_field = Publication._meta.get_field(name)
        try:
            model_field.clean(value, None)
        except ValidationError as exc:
            result.errors.setdefault(name, exc.messages)
    return result

from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from .importers import PublicationImportError, find_duplicates, parse_publication
from .models import Publication

FIXTURES = Path(__file__).parent / 'test_data'


class ParserTests(SimpleTestCase):
    def test_publisher_exports_match(self):
        results = []
        for extension in ('bib', 'ris'):
            upload = SimpleUploadedFile('article.' + extension, (FIXTURES / ('article.' + extension)).read_bytes())
            result = parse_publication(upload)
            self.assertEqual(result.errors, {})
            self.assertEqual(result.data['year'], 2026)
            self.assertEqual(result.data['doi'], '10.1016/j.radphyschem.2025.113557')
            self.assertEqual(result.data['pages'], '113557')
            self.assertFalse(result.data['is_published'])
            self.assertIn('Vladimir S. Sulaev', result.data['authors_text'])
            self.assertTrue(result.unmapped_fields)
            results.append(result.data)
        self.assertEqual(*results)

    def test_latex_names_strings_and_unicode(self):
        result = parse_publication(r'''@string{journalname = "Журнал"}
@article{key, title={An {FTIR} study of {\"o} and \&},
 author={Иванов, Иван and {Research and Development Team}},
 year=2025, journal=journalname, pages={1--12}}''')
        self.assertEqual(result.errors, {})
        self.assertEqual(result.data['title'], 'An FTIR study of ö and &')
        self.assertEqual(result.data['authors_text'], 'Иван Иванов; Research and Development Team')
        self.assertEqual(result.data['venue'], 'Журнал')
        self.assertEqual(result.data['pages'], '1–12')

    def test_unknown_type_and_fields(self):
        for text in ('@strange{k,title={Title},year={2025},author={Author},custom={value}}',
                     'TY  - XYZ\nTI  - Title\nPY  - 2025\nAU  - Author\nZZ  - value\nER  -'):
            result = parse_publication(text)
            self.assertEqual(result.data['kind'], 'other')
            self.assertEqual(len(result.warnings), 2)
            self.assertTrue(result.unmapped_fields)
            self.assertNotIn('note', result.data)

    def test_incomplete_record_can_be_corrected_in_form(self):
        result = parse_publication('@article{k,title={Title}}')
        self.assertEqual(set(result.errors), {'year', 'authors_text'})

    def test_reject_invalid_and_multiple_records(self):
        valid_bib = '@article{k,title={Title}}'
        valid_ris = 'TY  - JOUR\nTI  - Title\nER  -\n'
        for text in ('', 'garbage', '@article{k,title={broken}',
                     valid_bib + '\n@article{broken', valid_bib * 2,
                     valid_ris * 2, valid_ris + 'TY  - JOUR\nTI  - unfinished',
                     'TY  - JOUR\nTI  - missing end', valid_ris + 'garbage'):
            with self.subTest(text=text), self.assertRaises(PublicationImportError):
                parse_publication(text)

    def test_ris_dates_pages_and_continuations(self):
        result = parse_publication('TY  - CHAP\nTI  - Title\nAU  - Smith, Jane\n'
                                   'DA  - 2024/01/01\nT2  - Book\nSP  - 10\nEP  - 20\n'
                                   'AB  - First line\nsecond line\nER  -')
        self.assertEqual(result.errors, {})
        self.assertEqual(result.data['kind'], 'chapter')
        self.assertEqual(result.data['abstract'], 'First line second line')
        self.assertEqual(result.data['pages'], '10–20')

    def test_encoding_and_size(self):
        for source in (b'\xff', b'x' * (2 * 1024 * 1024 + 1)):
            with self.assertRaises(PublicationImportError):
                parse_publication(source)
        self.assertEqual(parse_publication(b'\xef\xbb\xbf@article{k,title={Title}}').data['title'], 'Title')


class DuplicateTests(TestCase):
    def test_normalized_doi_matches_unpublished_without_writes(self):
        publication = Publication.objects.create(title='Existing', year=2026, authors_text='A',
                                                 doi='https://doi.org/10.1234/ABC')
        result = parse_publication('@article{k,title={New},year=2026,author={A},doi={doi:10.1234/abc}}')
        matches = find_duplicates(result)
        self.assertEqual([(m.publication.pk, m.reason) for m in matches], [(publication.pk, 'doi')])
        self.assertEqual(find_duplicates(result, exclude_pk=publication.pk), [])
        self.assertEqual(Publication.objects.count(), 1)

    def test_title_year_fallback(self):
        publication = Publication.objects.create(title='A study: FTIR', year=2026, authors_text='A')
        result = parse_publication('@article{k,title={A STUDY — FTIR},year=2026,author={A}}')
        self.assertEqual(find_duplicates(result)[0].publication.pk, publication.pk)
        result.data['year'] = 2025
        self.assertEqual(find_duplicates(result), [])

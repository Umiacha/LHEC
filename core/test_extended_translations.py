from django.contrib import admin
from django.contrib.auth.models import AnonymousUser, User
from django.template.loader import get_template
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from core.models import GalleryPhoto
from education.models import LabWork, Lecture, LectureCourse, LectureFile, TeachingMaterial
from publications.models import Publication
from research.models import Diploma, Dissertation, ProjectParticipation, ResearchProject
from users.models import AcademicDegree, AcademicTitle, EducationStatus, Employee, EngineerPosition, SciencePosition


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ExtendedTranslationTests(TestCase):
    def setUp(self):
        self.addCleanup(translation.deactivate)

    def test_history_prose_and_all_statistics_branches_are_translated(self):
        request = RequestFactory().get('/en/about/history/')
        request.user = AnonymousUser()
        with translation.override('en'):
            for doctors, candidates in ((0, 0), (1, 0), (0, 1), (2, 3)):
                with self.subTest(doctors=doctors, candidates=candidates):
                    html = get_template('core/history.html').render({'staff_statistics': {
                        'total': 7, 'scientific': 5, 'doctors': doctors, 'candidates': candidates,
                    }}, request=request)
                    self.assertIn('The world’s first course in radiation chemistry', html)
                    self.assertIn('Vladimir I. Feldman', html)
                    self.assertIn('7 staff members, including 5 researchers', html)
                    # The linked article retains its original official title.
                    self.assertNotRegex(html.replace('История радиационной химии', ''), '[А-Яа-яЁё]')

    def test_project_and_external_participant_render_in_english(self):
        project = ResearchProject.objects.create(
            name='Русский проект', name_en='English project', slug='translated',
            start_year=2025, end_year=2030, is_published=True,
            abstract_en='English-only abstract', funding_source_en='English funder',
            customer_en='English customer', funding_program_en='English programme',
            funding_kind=ResearchProject.FundingKind.GRANT,
        )
        ProjectParticipation.objects.create(project=project, external_name='Русское имя',
            external_name_en='External Researcher', external_organization='Организация',
            external_organization_en='External Organization')
        with translation.override('en'):
            response = self.client.get(reverse('research:project_detail', args=[project.slug]))
        for text in ('English project', 'English-only abstract', 'English funder',
                     'English customer', 'English programme', 'External Researcher',
                     'External Organization', 'Grant'):
            self.assertContains(response, text)
        self.assertNotContains(response, 'Русское имя')
        self.assertContains(self.client.get('/en/science/'), 'English project')
        with translation.override('en'):
            self.assertContains(self.client.get(reverse('research:projects')), 'Current')
        with translation.override('ru'):
            self.assertEqual(project.localized_name, 'Русский проект')

    def test_publication_preserves_metadata_and_searches_english_authors(self):
        publication = Publication.objects.create(
            title='Оригинальное название статьи', authors_text='Оригинальные авторы',
            authors_text_en='Manual English Authors', note_en='English-only laboratory note',
            venue='Оригинальный журнал', year=2026, is_published=True, is_on_homepage=True,
        )
        with translation.override('en'):
            url = reverse('publications:publication', args=[publication.pk])
            search = reverse('publications:publications')
        response = self.client.get(url)
        for text in ('Оригинальное название статьи', 'Оригинальный журнал',
                     'Manual English Authors', 'English-only laboratory note', 'Article'):
            self.assertContains(response, text)
        self.assertContains(self.client.get('/en/'), 'English-only laboratory note')
        self.assertContains(self.client.get(search, {'q': 'Manual English'}), publication.title)
        self.assertNotContains(response, 'Оригинальные авторы')
        publication.authors_text_en = ' '
        with translation.override('en'):
            self.assertEqual(publication.localized_authors_text, 'Оригинальные авторы')

    def test_gallery_caption_is_used_for_text_alt_and_link_label(self):
        GalleryPhoto.objects.bulk_create([GalleryPhoto(
            caption='Русская подпись', caption_en='English photo caption', year=2026,
            image='gallery/original.jpg', thumbnail='gallery/thumbnail.jpg', is_published=True,
        )])
        response = self.client.get('/en/gallery/')
        self.assertContains(response, 'English photo caption', count=3)
        self.assertContains(response, 'Open photo: English photo caption (in a new tab)')
        self.assertNotContains(response, 'Русская подпись')

    def test_fixed_position_degree_and_education_labels_follow_language(self):
        employee = Employee(science_position=SciencePosition.SENIOR_RESEARCH_FELLOW,
            engineer_position=EngineerPosition.LEADING_ENGINEER,
            education_status=EducationStatus.STUDENT, study_year=3,
            academic_degree=AcademicDegree.CANDIDATE_CHEMISTRY,
            academic_title=AcademicTitle.DOCENT)
        with translation.override('en'):
            self.assertEqual(employee.get_science_position_display(), 'Senior Researcher')
            self.assertEqual(employee.get_engineer_position_display(), 'Leading Engineer')
            self.assertEqual(employee.education_label, 'Student, year 3')
            self.assertEqual(employee.get_academic_degree_display(), 'PhD in Chemistry')
            self.assertEqual(employee.get_academic_title_display(), 'Associate Professor')
        with translation.override('ru'):
            self.assertEqual(employee.education_label, 'Студент, 3 курс')
            self.assertEqual(employee.get_science_position_display(), 'с.н.с.')
        self.assertEqual(employee.science_position, 'senior_research_fellow')

    def test_teaching_descriptions_translate_but_document_titles_stay_original(self):
        lab = LabWork.objects.create(title='Официальное название работы', slug='lab',
            short_description='Описание', short_description_en='English summary',
            description_en='English-only lab description', equipment_en='English equipment')
        TeachingMaterial.objects.create(title='Название документа', description_en='English material',
            file='education/materials/example.pdf', lab_work=lab)
        response = self.client.get('/en/students/study_materials/')
        for text in ('Официальное название работы', 'Название документа', 'English summary',
                     'English-only lab description', 'English equipment', 'English material'):
            self.assertContains(response, text)
        course = LectureCourse.objects.create(title='Название курса', slug='course',
            description_en='English course description', is_published=True)
        lecture = Lecture.objects.create(course=course, title='Название лекции',
            note_en='English lecturer note', is_published=True)
        LectureFile.objects.create(lecture=lecture, title='Подпись', title_en='English file label',
            file='education/lectures/example.pdf')
        user = User.objects.create_superuser('reader', password='test')
        self.client.force_login(user)
        with translation.override('en'):
            response = self.client.get(reverse('education:lecture_course_detail', args=[course.slug]))
        for text in ('Название курса', 'Название лекции', 'English course description',
                     'English lecturer note', 'English file label'):
            self.assertContains(response, text)

    def test_added_translations_are_editable_in_registered_admin_forms(self):
        request = RequestFactory().get('/admin/')
        request.user = User(is_superuser=True, is_staff=True)
        for model in (ResearchProject, Dissertation, Diploma, GalleryPhoto, Publication,
                      LabWork, TeachingMaterial, LectureCourse, Lecture):
            with self.subTest(model=model.__name__):
                form = admin.site._registry[model].get_form(request)
                fields = [field.name for field in model._meta.fields if field.name.endswith('_en')]
                self.assertTrue(fields)
                for field in fields:
                    self.assertIn(field, form.base_fields)

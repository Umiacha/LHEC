from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse

from publications.models import Publication
from research.models import Diploma, Dissertation, ResearchDirection, ResearchMembership
from users.models import Employee
from users.roles import EMPLOYEE_GROUP_NAME


class ResearchDirectionTests(TestCase):
    def test_team_includes_leader_once(self):
        leader = Employee.objects.create(first_name='Иван', last_name='Иванов')
        employee = Employee.objects.create(first_name='Пётр', last_name='Петров')
        direction = ResearchDirection.objects.create(
            name='Направление', slug='direction', leader=leader,
        )
        direction.employees.add(employee)
        self.assertSetEqual(set(direction.get_team()), {leader, employee})
        direction.employees.add(leader)
        self.assertEqual(direction.get_team().count(), 2)

    def test_deleting_leader_preserves_direction(self):
        leader = Employee.objects.create(first_name='Иван', last_name='Иванов')
        direction = ResearchDirection.objects.create(
            name='Направление', slug='direction', leader=leader,
        )
        leader.delete()
        direction.refresh_from_db()
        self.assertIsNone(direction.leader)
        self.assertFalse(direction.get_team().exists())

    def test_publication_can_belong_to_multiple_directions(self):
        first = ResearchDirection.objects.create(name='Первое', slug='first')
        second = ResearchDirection.objects.create(name='Второе', slug='second')
        publication = Publication.objects.create(
            title='Статья', year=2026, authors_text='Иванов И.',
        )
        publication.research_directions.add(first, second)
        self.assertEqual(first.publications.get(), publication)
        self.assertEqual(second.publications.get(), publication)
        first.delete()
        self.assertEqual(publication.research_directions.get(), second)


class ResearchMembershipTests(TestCase):
    def test_explicit_membership_and_reverse_access(self):
        employee = Employee.objects.create(first_name='Иван', last_name='Иванов')
        direction = ResearchDirection.objects.create(name='Направление', slug='direction')
        membership = ResearchMembership.objects.create(direction=direction, employee=employee)
        self.assertEqual(employee.research_directions.get(), direction)
        self.assertEqual(direction.employees.get(), employee)
        self.assertEqual(employee.research_memberships.get(), membership)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ResearchMembership.objects.create(direction=direction, employee=employee)


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
)
class ResearchViewTests(TestCase):
    def setUp(self):
        from django.urls import reverse
        self.direction = ResearchDirection.objects.create(
            name='Открытое направление', slug='visible', is_published=True,
        )
        self.url = reverse('research:direction_detail', args=[self.direction.slug])

    def test_science_lists_only_published_directions(self):
        ResearchDirection.objects.create(name='Скрытое направление', slug='hidden')
        response = self.client.get('/science/')
        self.assertContains(response, self.url)
        self.assertNotContains(response, 'Скрытое направление')

    def test_hidden_and_missing_directions_return_404(self):
        self.direction.is_published = False
        self.direction.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get('/science/directions/missing/').status_code, 404)

    def test_detail_filters_people_and_publications(self):
        leader = Employee.objects.create(first_name='Иван', last_name='Руководитель')
        hidden = Employee.objects.create(first_name='Пётр', last_name='Скрытый', is_published=False)
        self.direction.leader = leader
        self.direction.save()
        self.direction.employees.add(leader, hidden)
        visible = Publication.objects.create(title='Открытая статья', year=2026, is_published=True)
        draft = Publication.objects.create(title='Черновая статья', year=2026)
        unrelated = Publication.objects.create(title='Другая статья', year=2026, is_published=True)
        self.direction.publications.add(visible, draft)
        response = self.client.get(self.url)
        self.assertEqual(response.context['leader'], leader)
        self.assertEqual(list(response.context['employees']), [])
        self.assertEqual(list(response.context['publications']), [visible])
        self.assertNotContains(response, hidden.last_name)
        self.assertNotContains(response, draft.title)
        self.assertNotContains(response, unrelated.title)
        leader.is_published = False
        leader.save()
        self.assertIsNone(self.client.get(self.url).context['leader'])

    def test_publications_pagination(self):
        for index in range(21):
            self.direction.publications.create(title=f'Статья {index}', year=2026, is_published=True)
        first = self.client.get(self.url)
        second = self.client.get(self.url, {'page': 2})
        self.assertEqual(len(first.context['publications']), 20)
        self.assertEqual(len(second.context['publications']), 1)
        self.assertContains(first, '?page=2')


class ResearchProjectTests(TestCase):
    def setUp(self):
        from .models import ResearchProject
        self.project = ResearchProject.objects.create(
            name='Проект', slug='project', start_year=2026, end_year=2028,
        )
        self.employee = Employee.objects.create(first_name='Иван', last_name='Иванов')

    def test_staff_leader_and_external_executor(self):
        from .models import ProjectParticipation
        leader = ProjectParticipation(
            project=self.project, employee=self.employee, role=ProjectParticipation.Role.LEADER,
        )
        leader.full_clean()
        leader.save()
        external = ProjectParticipation(
            project=self.project, external_name='Пётр Петров', external_organization='МГУ',
        )
        external.full_clean()
        external.save()
        self.assertEqual(self.project.participations.count(), 2)
        self.assertEqual(self.employee.project_participations.get(), leader)

    def test_identity_requires_employee_or_external_name(self):
        from django.core.exceptions import ValidationError
        from .models import ProjectParticipation
        for values in ({}, {'employee': self.employee, 'external_name': 'Пётр Петров'},
                       {'external_name': '   '}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                ProjectParticipation(project=self.project, **values).full_clean()

    def test_database_rejects_duplicate_employee_and_second_leader(self):
        from .models import ProjectParticipation
        ProjectParticipation.objects.create(
            project=self.project, employee=self.employee, role='leader',
        )
        for values in ({'employee': self.employee}, {'external_name': 'Пётр Петров', 'role': 'leader'}):
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                ProjectParticipation.objects.create(project=self.project, **values)

    def test_invalid_years(self):
        from django.core.exceptions import ValidationError
        self.project.end_year = 2025
        with self.assertRaises(ValidationError):
            self.project.full_clean()

    def test_deleting_employee_preserves_project_participation(self):
        from django.db.models.deletion import ProtectedError
        from .models import ProjectParticipation
        ProjectParticipation.objects.create(project=self.project, employee=self.employee)
        with self.assertRaises(ProtectedError):
            self.employee.delete()


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ProjectViewTests(TestCase):
    def setUp(self):
        from .models import ResearchProject
        self.project = ResearchProject.objects.create(
            name='Проект для сайта', slug='public-project', start_year=2020,
            end_year=2022, is_published=True, funding_number='22-001',
        )

    def test_list_route_and_published_completed_project(self):
        from django.urls import resolve, reverse
        from . import views
        from .models import ResearchProject
        ResearchProject.objects.create(name='Черновик проекта', slug='draft', start_year=2026, end_year=2028)
        url = reverse('research:projects')
        self.assertEqual(url, '/science/projects/')
        self.assertEqual(resolve(url).func, views.projects)
        response = self.client.get(url)
        self.assertContains(response, self.project.name)
        self.assertNotContains(response, 'Черновик проекта')
        self.assertContains(response, reverse('research:project_detail', args=[self.project.slug]))
        self.assertContains(self.client.get('/science/'), url)

    def test_detail_participants_and_metadata(self):
        from .models import ProjectParticipation
        leader = Employee.objects.create(first_name='Иван', last_name='Руководитель')
        hidden = Employee.objects.create(first_name='Пётр', last_name='Скрытый', is_published=False)
        ProjectParticipation.objects.create(project=self.project, employee=leader, role='leader')
        ProjectParticipation.objects.create(project=self.project, employee=hidden)
        ProjectParticipation.objects.create(project=self.project, external_name='Внешний исполнитель', external_organization='МГУ')
        response = self.client.get('/science/projects/public-project/')
        self.assertContains(response, 'Руководитель')
        self.assertContains(response, 'Внешний исполнитель')
        self.assertContains(response, 'МГУ')
        self.assertNotContains(response, 'Скрытый')
        self.assertContains(response, '<details')
        self.assertContains(response, '22-001')

    def test_hidden_and_missing_projects_return_404(self):
        self.project.is_published = False
        self.project.save()
        self.assertEqual(self.client.get('/science/projects/public-project/').status_code, 404)
        self.assertEqual(self.client.get('/science/projects/missing/').status_code, 404)


class ProjectAdminTests(TestCase):
    def test_inline_validates_new_project_participations(self):
        from django.forms.models import inlineformset_factory
        from .admin import ProjectParticipationFormSet
        from .models import ProjectParticipation, ResearchProject
        formset_class = inlineformset_factory(
            ResearchProject, ProjectParticipation, formset=ProjectParticipationFormSet,
            fields=('employee', 'external_name', 'external_organization', 'role', 'sort_order'),
        )
        data = {
            'participations-TOTAL_FORMS': '2', 'participations-INITIAL_FORMS': '0',
            'participations-0-external_name': 'Иван Иванов',
            'participations-0-role': 'leader', 'participations-0-sort_order': '0',
            'participations-1-external_name': 'Пётр Петров',
            'participations-1-role': 'leader', 'participations-1-sort_order': '1',
        }
        formset = formset_class(data, instance=ResearchProject())
        self.assertFalse(formset.is_valid())
        self.assertIn('только один руководитель', str(formset.non_form_errors()))
        data['participations-1-role'] = 'executor'
        data['participations-1-external_name'] = 'Иван Иванов'
        formset = formset_class(data, instance=ResearchProject())
        self.assertFalse(formset.is_valid())
        self.assertIn('дважды', str(formset.non_form_errors()))
        data['participations-1-external_name'] = 'Пётр Петров'
        self.assertTrue(formset_class(data, instance=ResearchProject()).is_valid())

    def test_project_admin_pages(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        from .models import ResearchProject
        user = get_user_model().objects.create_superuser(username='project-admin', password='test-password')
        self.client.force_login(user)
        project = ResearchProject.objects.create(name='Проект', slug='admin-project', start_year=2026, end_year=2028)
        for url in (
            reverse('admin:research_researchproject_changelist'),
            reverse('admin:research_researchproject_add'),
            reverse('admin:research_researchproject_change', args=[project.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_project_list_groups_by_year(self):
        from unittest.mock import patch
        from datetime import date
        from .models import ResearchProject
        cases = [
            ('Заканчивается сейчас', 2025, 2026),
            ('Начинается сейчас', 2026, 2028),
            ('Завершен', 2020, 2025),
            ('Будущий', 2027, 2029),
        ]
        for index, (name, start, end) in enumerate(cases):
            ResearchProject.objects.create(name=name, slug=f'group-{index}', start_year=start, end_year=end, is_published=True)
        with patch('research.views.timezone.localdate', return_value=date(2026, 10, 29)):
            response = self.client.get('/science/projects/')
        groups = response.context['project_groups']
        self.assertEqual([group['title'] for group in groups], ['Текущие', 'Завершенные', 'Предстоящие'])
        self.assertSetEqual({p.name for p in groups[0]['projects']}, {'Заканчивается сейчас', 'Начинается сейчас'})
        self.assertEqual([p.name for p in groups[1]['projects']], ['Завершен'])
        self.assertEqual([p.name for p in groups[2]['projects']], ['Будущий'])


class DiplomaTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = override_settings(PRIVATE_PUBLICATIONS_ROOT=directory.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.author = Employee.objects.create(first_name='Иван', last_name='Иванов')
        self.diploma = Diploma.objects.create(
            title='Диплом', author=self.author, year=2020, level=Diploma.Level.SPECIALIST,
            external_url='https://example.org/diploma', is_published=True,
            file=SimpleUploadedFile('diploma.pdf', b'%PDF-diploma'),
        )
        self.url = self.diploma.file.url

    def test_file_path_and_author_protection(self):
        self.assertEqual(self.diploma.file.name, 'diplomas/2020/diploma.pdf')
        from django.conf import settings
        self.assertFalse(Path(self.diploma.file.path).is_relative_to(settings.MEDIA_ROOT))
        with self.assertRaises(ProtectedError):
            self.author.delete()

    def test_permissions(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)
        user = get_user_model().objects.create_user(username='staff', is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        user.groups.add(Group.objects.get(name=EMPLOYEE_GROUP_NAME))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('private', response['Cache-Control'])
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertEqual(b''.join(response.streaming_content), b'%PDF-diploma')

    def test_missing_and_unpublished_file(self):
        user = get_user_model().objects.create_superuser(username='admin', password='password')
        self.client.force_login(user)
        self.diploma.is_published = False
        self.diploma.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.diploma.is_published = True
        self.diploma.save()
        Path(self.diploma.file.path).unlink()
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_admin_can_create_without_file(self):
        user = get_user_model().objects.create_superuser(username='admin', password='password')
        self.client.force_login(user)
        response = self.client.post(reverse('admin:research_diploma_add'), {
            'title': 'Новая ВКР', 'external_url': 'https://example.org/new',
            'author': self.author.pk, 'year': 2021, 'level': Diploma.Level.MASTER,
            'supervisors': [self.author.pk], 'external_supervisors': 'Внешний руководитель',
            'sort_order': 0, '_save': 'Сохранить',
        })
        self.assertEqual(response.status_code, 302)
        diploma = Diploma.objects.get(title='Новая ВКР')
        self.assertFalse(diploma.file)
        self.assertFalse(diploma.is_published)
        self.assertEqual(list(diploma.supervisors.all()), [self.author])

    def test_science_card_and_publication_visibility(self):
        supervisor = Employee.objects.create(first_name='Пётр', last_name='Петров', is_published=False)
        self.diploma.supervisors.add(supervisor)
        self.diploma.external_supervisors = 'Внешний руководитель'
        self.diploma.save()
        page = reverse('research:science')
        response = self.client.get(page)
        self.assertContains(response, self.diploma.external_url)
        self.assertContains(response, self.diploma.get_level_display())
        self.assertContains(response, reverse('users:employe_card', args=[self.author.pk]))
        self.assertContains(response, 'Внешний руководитель')
        self.assertContains(response, 'Петров')
        self.assertNotContains(response, reverse('users:employe_card', args=[supervisor.pk]))
        self.assertNotContains(response, self.url)
        self.assertLess(response.content.index(b'id="dissertations"'), response.content.index(b'id="diplomas"'))
        self.author.is_published = False
        self.author.save()
        self.assertNotContains(self.client.get(page), reverse('users:employe_card', args=[self.author.pk]))
        self.diploma.is_published = False
        self.diploma.save()
        self.assertNotContains(self.client.get(page), self.diploma.external_url)

    def test_science_download_requires_employee_and_file(self):
        page = reverse('research:science')
        user = get_user_model().objects.create_user(username='reader', is_staff=True)
        self.client.force_login(user)
        self.assertNotContains(self.client.get(page), self.url)
        user.groups.add(Group.objects.get(name=EMPLOYEE_GROUP_NAME))
        self.assertContains(self.client.get(page), self.url)
        self.diploma.file = ''
        self.diploma.save()
        self.assertNotContains(self.client.get(page), 'Скачать ВКР')


class DissertationTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = override_settings(
            PRIVATE_PUBLICATIONS_ROOT=directory.name,
            STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
            },
        )
        settings.enable()
        self.addCleanup(settings.disable)
        self.dissertation = Dissertation.objects.create(
            title='Название диссертации', author='Иванов Иван', year=2021,
            specialty='02.00.09 — Химия высоких энергий', supervisors='Руководитель',
            external_url='https://example.org/thesis/', is_published=True,
            file=SimpleUploadedFile('thesis.pdf', b'%PDF-thesis'),
        )
        self.url = self.dissertation.file.url
        self.page = reverse('research:science')
        self.employee = get_user_model().objects.create_user(username='employee')
        self.employee.groups.add(Group.objects.get(name=EMPLOYEE_GROUP_NAME))

    def test_file_directory_uses_defense_year(self):
        self.assertEqual(self.dissertation.file.name, 'dissertations/2021/thesis.pdf')

    def test_public_card_links_to_source_and_hides_download(self):
        response = self.client.get(self.page)
        for value in ('Название диссертации', 'Иванов Иван', '2021', 'Руководитель', self.dissertation.external_url):
            self.assertContains(response, value)
        self.assertNotContains(response, self.url)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertFalse(Path(self.dissertation.file.path).is_relative_to(Path('media').resolve()))

    def test_login_and_staff_flag_alone_do_not_grant_access(self):
        for staff in (False, True):
            user = get_user_model().objects.create_user(username=f'user{staff}', is_staff=staff)
            self.client.force_login(user)
            self.assertNotContains(self.client.get(self.page), self.url)
            self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_employee_and_administrator_can_download(self):
        admin = get_user_model().objects.create_superuser(username='admin', password='password')
        for user in (self.employee, admin):
            self.client.force_login(user)
            self.assertContains(self.client.get(self.page), self.url)
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('attachment;', response['Content-Disposition'])
            self.assertIn('private', response['Cache-Control'])
            self.assertEqual(b''.join(response.streaming_content), b'%PDF-thesis')

    def test_unpublished_and_missing_files(self):
        self.client.force_login(self.employee)
        self.dissertation.is_published = False
        self.dissertation.save()
        self.assertNotContains(self.client.get(self.page), self.dissertation.title)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.dissertation.is_published = True
        self.dissertation.save()
        Path(self.dissertation.file.path).unlink()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.dissertation.file = ''
        self.dissertation.save()
        self.assertNotContains(self.client.get(self.page), 'Скачать диссертацию')

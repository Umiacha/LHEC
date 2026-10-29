from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from publications.models import Publication
from users.models import Employee

from .models import ResearchDirection, ResearchMembership


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

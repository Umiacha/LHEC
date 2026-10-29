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

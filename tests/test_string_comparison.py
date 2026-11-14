from django.apps import apps
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.expressions import RawSQL
from django.forms import modelform_factory
from django.forms.models import inlineformset_factory
from django.test import TestCase

from education.models import LabWork, LectureCourse
from research.admin import ProjectParticipationFormSet
from research.models import ProjectParticipation, ResearchDirection, ResearchProject
from users.forms import LoginForm, RoleUserCreationForm
from users.models import Employee
from users.roles import UserRole


class StringComparisonTests(TestCase):
    def test_standard_user_case_uniqueness_creation_form_and_login(self):
        user = User.objects.create_user(username='Admin', password='test-password-915')
        self.assertEqual(authenticate(username='ADMIN', password='test-password-915'), user)
        form = LoginForm(data={'username': 'ＡdMiN', 'password': 'test-password-915'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.get_user(), user)
        form = RoleUserCreationForm(data={
            'username': 'ADMIN', 'password1': 'another-password-816',
            'password2': 'another-password-816', 'role': UserRole.EMPLOYEE,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)
        with self.assertRaises(ValidationError):
            User(username='ADMIN').full_clean(exclude=('password',))
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create([User(username='ADMIN')])

    def test_standard_user_distinguishes_accents_and_yo(self):
        for username in ('Семенов', 'Семёнов', 'resume', 'résumé'):
            User.objects.create_user(username=username)
            self.assertEqual(User.objects.filter(username=username.upper()).count(), 1)
        self.assertEqual(User.objects.count(), 4)
        self.assertEqual(User.objects.filter(username__icontains='СЕМЁ').count(), 1)

    def test_names_nfc_outer_spaces_search_and_literal_bulk_writes(self):
        person = Employee.objects.create(first_name='  Пе\u0308тр ', last_name=' Семёнов ')
        self.assertEqual(person.first_name, 'Пётр')
        self.assertEqual(person.last_name, 'Семёнов')
        self.assertTrue(Employee.objects.filter(last_name='СЕМЁНОВ').exists())
        self.assertFalse(Employee.objects.filter(last_name='Семенов').exists())
        self.assertTrue(Employee.objects.filter(first_name__icontains='ПЁТ').exists())
        self.assertFalse(Employee.objects.filter(first_name__icontains='ПЕТ').exists())
        Employee.objects.filter(pk=person.pk).update(last_name='  Smith  ')
        person.refresh_from_db()
        self.assertEqual(person.last_name, 'Smith')
        self.assertTrue(Employee.objects.filter(last_name__icontains='SMI').exists())
        Employee.objects.bulk_create([Employee(first_name='  Jose\u0301 ', last_name='  Test ')])
        self.assertEqual(Employee.objects.get(last_name='test').first_name, 'José')

    def test_russian_and_english_sorting(self):
        names = ['Яковлев', 'Семёнов', 'Белов', 'Семенов', 'Абрамов', 'Clark', 'Baker', 'Adams']
        Employee.objects.bulk_create([Employee(first_name='Имя', last_name=name) for name in names])
        self.assertEqual(list(Employee.objects.order_by('last_name', 'pk').values_list('last_name', flat=True)), [
            'Adams', 'Baker', 'Clark', 'Абрамов', 'Белов', 'Семенов', 'Семёнов', 'Яковлев',
        ])
        Employee.objects.all().delete()
        for index, name in enumerate(('Яковлев', 'Семёнов', 'Семенов', 'Белов', 'Абрамов')):
            Employee.objects.create(first_name=str(index), last_name=name)
        self.assertEqual(list(Employee.objects.by_position().values_list('last_name', flat=True)), [
            'Абрамов', 'Белов', 'Семенов', 'Семёнов', 'Яковлев',
        ])

    def test_all_slugs_normalize_and_reject_case_duplicates(self):
        for model, defaults in (
            (ResearchDirection, {'name': 'Направление'}),
            (ResearchProject, {'name': 'Проект', 'start_year': 2026, 'end_year': 2028}),
            (LabWork, {'title': 'Работа', 'short_description': 'Описание'}),
            (LectureCourse, {'title': 'Курс'}),
        ):
            with self.subTest(model=model):
                item = model.objects.create(slug='  My-Slug ', **defaults)
                self.assertEqual(item.slug, 'my-slug')
                self.assertEqual(model.objects.get(slug='MY-SLUG'), item)
                form_class = modelform_factory(model, fields=('slug',))
                form = form_class(data={'slug': 'MY-SLUG'})
                self.assertFalse(form.is_valid())
                self.assertIn('slug', form.errors)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    model.objects.bulk_create([model(slug='My-Slug', **defaults)])
                other = model.objects.create(slug='other-slug', **defaults)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    model.objects.filter(pk=other.pk).update(slug=RawSQL('%s', ['MY-SLUG']))

    def test_external_identity_uses_case_insensitive_accent_sensitive_unique_index(self):
        project = ResearchProject.objects.create(name='Проект', slug='project', start_year=2026, end_year=2028)
        first = ProjectParticipation.objects.create(
            project=project, external_name=' Семенов ', external_organization=' МГУ ',
        )
        first.refresh_from_db()
        self.assertEqual((first.external_identity_name, first.external_identity_organization), ('Семенов', 'МГУ'))
        self.assertEqual(ProjectParticipation.objects.filter(
            external_identity_name='СЕМЕНОВ', external_identity_organization='мгу',
        ).count(), 1)
        for values in (
            {'external_name': 'СЕМЕНОВ', 'external_organization': 'мгу'},
            {'external_name': 'Семенов', 'external_organization': 'МГУ'},
        ):
            with self.assertRaises(IntegrityError), transaction.atomic():
                ProjectParticipation.objects.bulk_create([ProjectParticipation(project=project, **values)])
            with self.assertRaises(ValidationError):
                ProjectParticipation(project=project, **values).full_clean()
        second = ProjectParticipation.objects.create(
            project=project, external_name='Семёнов', external_organization='МГУ',
        )
        for bulk in (False, True):
            with self.subTest(bulk=bulk), self.assertRaises(IntegrityError), transaction.atomic():
                if bulk:
                    second.external_name = 'СЕМЕНОВ'
                    ProjectParticipation.objects.bulk_update([second], ['external_name'])
                else:
                    ProjectParticipation.objects.filter(pk=second.pk).update(external_name='СЕМЕНОВ')
        first.refresh_from_db()
        self.assertEqual(first.external_identity_name, 'Семенов')
        self.assertEqual(first.external_identity_organization, 'МГУ')
        ProjectParticipation.objects.create(project=project, external_name='José', external_organization='Institut')
        ProjectParticipation.objects.create(project=project, external_name='Jose', external_organization='Institut')
        ProjectParticipation.objects.create(project=project, external_name='Jose', external_organization='Ínstitut')

    def test_inline_duplicates_follow_database_collation(self):
        formset_class = inlineformset_factory(
            ResearchProject, ProjectParticipation, formset=ProjectParticipationFormSet,
            fields=('external_name', 'external_organization', 'role'), extra=0,
        )
        data = {'participations-TOTAL_FORMS': '2', 'participations-INITIAL_FORMS': '0'}
        for index, name in enumerate((' Семенов ', 'СЕМЕНОВ')):
            data.update({
                f'participations-{index}-external_name': name,
                f'participations-{index}-external_organization': 'МГУ' if index else 'мгу',
                f'participations-{index}-role': 'executor',
            })
        formset = formset_class(data, instance=ResearchProject())
        self.assertFalse(formset.is_valid())
        self.assertIn('Один человек не может участвовать в проекте дважды.', formset.non_form_errors())
        data['participations-1-external_name'] = 'Семёнов'
        formset = formset_class(data, instance=ResearchProject())
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_actual_column_collations_include_standard_auth_and_generated_columns(self):
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT TABLE_NAME, COLUMN_NAME, COLLATION_NAME FROM information_schema.COLUMNS '
                'WHERE TABLE_SCHEMA = DATABASE() AND COLLATION_NAME IS NOT NULL',
            )
            actual = {(table, column): collation for table, column, collation in cursor.fetchall()}
        for model in apps.get_models():
            for field in model._meta.local_fields:
                expected = field.db_parameters(connection).get('collation')
                if expected:
                    self.assertEqual(actual[model._meta.db_table, field.column], expected)
        for field in ('username', 'first_name', 'last_name'):
            self.assertEqual(actual['auth_user', field], 'utf8mb4_0900_as_ci')
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT COLUMN_NAME, GENERATION_EXPRESSION FROM information_schema.COLUMNS '
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'research_projectparticipation' "
                "AND COLUMN_NAME IN ('external_identity_name', 'external_identity_organization')",
            )
            generated = cursor.fetchall()
        self.assertEqual(len(generated), 2)
        self.assertTrue(all(expression for name, expression in generated))

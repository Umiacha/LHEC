from copy import copy
from importlib import import_module

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase

from users.forms import EmployeeEditForm
from users.models import Employee, ScientificProfile


def profile_url(length):
    prefix = 'https://example.org/'
    return prefix + 'a' * (length - len(prefix))


class ScientificProfileTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(first_name='Иван', last_name='Иванов')

    def test_500_character_url_and_unique_employee_url(self):
        url = profile_url(500)
        profile = ScientificProfile(employee=self.employee, url=url)
        profile.full_clean()
        profile.save()
        profile.refresh_from_db()
        self.assertEqual(profile.url, url)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ScientificProfile.objects.create(employee=self.employee, url=url)
        other = Employee.objects.create(first_name='Пётр', last_name='Петров')
        ScientificProfile.objects.create(employee=other, url=url)

    def test_overlong_url_rejected_by_model_form_and_database(self):
        url = profile_url(501)
        with self.assertRaises(ValidationError):
            ScientificProfile(employee=self.employee, url=url).full_clean()
        form = EmployeeEditForm(instance=self.employee, data={
            'first_name': 'Иван', 'last_name': 'Иванов', 'scientific_profiles': url,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('scientific_profiles', form.errors)
        with self.assertRaises(DataError), transaction.atomic():
            ScientificProfile.objects.create(employee=self.employee, url=url)
        self.assertFalse(self.employee.scientific_profiles.exists())

    def test_form_accepts_500_character_url(self):
        url = profile_url(500)
        form = EmployeeEditForm(instance=self.employee, data={
            'first_name': 'Иван', 'last_name': 'Иванов', 'scientific_profiles': url,
        })
        self.assertTrue(form.is_valid(), form.errors)
        form.save_profiles(self.employee)
        self.assertEqual(self.employee.scientific_profiles.get().url, url)


class ScientificProfileMigrationTests(TransactionTestCase):
    def test_existing_long_column_is_checked_before_shrinking(self):
        migration = import_module('users.migrations.0004_scientificprofile_url_length')
        employee = Employee.objects.create(first_name='Иван', last_name='Иванов')
        field = ScientificProfile._meta.get_field('url')
        long_field = copy(field)
        long_field.max_length = 2000
        constraint = ScientificProfile._meta.constraints[0]
        # Reproduce the old column without its oversized index, which MySQL cannot create.
        with connection.schema_editor() as editor:
            editor.remove_constraint(ScientificProfile, constraint)
            editor.alter_field(ScientificProfile, field, long_field)
        try:
            profile = ScientificProfile.objects.create(employee=employee, url=profile_url(501))
            with connection.schema_editor() as editor:
                with self.assertRaisesRegex(RuntimeError, 'Значения не обрезаны'):
                    migration.check_url_lengths(apps, editor)
            profile.refresh_from_db()
            self.assertEqual(profile.url, profile_url(501))
            ScientificProfile.objects.filter(pk=profile.pk).update(url=profile_url(500))
            with connection.schema_editor() as editor:
                migration.check_url_lengths(apps, editor)
                migration.shrink_url(apps, editor)
            profile.refresh_from_db()
            self.assertEqual(profile.url, profile_url(500))
            with connection.cursor() as cursor:
                column = next(item for item in connection.introspection.get_table_description(
                    cursor, ScientificProfile._meta.db_table,
                ) if item.name == 'url')
            self.assertEqual(column.internal_size, 500)
        finally:
            ScientificProfile.objects.all().delete()
            with connection.schema_editor() as editor:
                editor.alter_field(ScientificProfile, long_field, field)
                editor.add_constraint(ScientificProfile, constraint)

from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError, connection, transaction
from django.test import TestCase

from users.forms import EmployeeEditForm
from users.models import Employee, ScientificProfile


def profile_url(length):
    prefix = 'https://example.org/'
    return prefix + 'a' * (length - len(prefix))


class ScientificProfileTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(first_name='Иван', last_name='Иванов')

    def test_url_path_and_query_case_are_preserved_by_form_and_database(self):
        urls = [
            'https://example.org/Profile?id=AbC',
            'https://example.org/profile?id=AbC',
            'https://example.org/Profile?id=abc',
        ]
        form = EmployeeEditForm(instance=self.employee, data={
            'first_name': 'Иван', 'last_name': 'Иванов',
            'scientific_profiles': '\n'.join(urls),
        })
        self.assertTrue(form.is_valid(), form.errors)
        form.save_profiles(self.employee)
        self.assertEqual(list(self.employee.scientific_profiles.values_list('url', flat=True)), urls)
        for url in urls:
            self.assertEqual(self.employee.scientific_profiles.filter(url=url).count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ScientificProfile.objects.create(employee=self.employee, url=urls[0])
        # Removing a URL must not retain another URL merely because its case matches.
        form = EmployeeEditForm(instance=self.employee, data={
            'first_name': 'Иван', 'last_name': 'Иванов', 'scientific_profiles': urls[0],
        })
        self.assertTrue(form.is_valid(), form.errors)
        form.save_profiles(self.employee)
        self.assertEqual(list(self.employee.scientific_profiles.values_list('url', flat=True)), urls[:1])

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

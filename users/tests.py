from django.test import TestCase
from django.urls import reverse

from .models import Employee, SciencePosition


class PeoplePageTests(TestCase):
    def test_list_shows_published_employee_with_link_and_fallback(self):
        employee = Employee.objects.create(
            last_name="Иванов",
            first_name="Иван",
            science_position=SciencePosition.RESEARCH_FELLOW,
        )
        Employee.objects.create(last_name="Скрытый", first_name="Сотрудник", is_published=False)

        response = self.client.get(reverse("users:people"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Иванов Иван")
        self.assertContains(response, employee.get_science_position_display())
        self.assertContains(response, reverse("users:employe_card", args=[employee.pk]))
        self.assertNotContains(response, "Скрытый")
        self.assertContains(response, "<svg", html=False)

    def test_card_of_unpublished_employee_is_not_public(self):
        employee = Employee.objects.create(last_name="Скрытый", first_name="Сотрудник", is_published=False)

        response = self.client.get(reverse("users:employe_card", args=[employee.pk]))

        self.assertEqual(response.status_code, 404)

# Create your tests here.

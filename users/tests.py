from django.test import TestCase
from django.contrib.auth.models import User
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


class EmployeeEditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="employee", password="test-password")
        self.employee = Employee.objects.create(
            last_name="Иванов", first_name="Иван", user=self.user,
        )
        self.edit_url = reverse("users:edit_employe_card", args=[self.employee.pk])

    def test_only_owner_sees_edit_link_and_can_open_form(self):
        card_url = reverse("users:employe_card", args=[self.employee.pk])
        self.assertNotContains(self.client.get(card_url), self.edit_url)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(card_url), self.edit_url)
        self.assertContains(self.client.get(self.edit_url), "Редактировать карточку")

    def test_guest_redirects_to_login_and_other_user_cannot_edit(self):
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("users:login"), response.url)

        other = User.objects.create_user(username="other", password="test-password")
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.edit_url).status_code, 404)
        self.assertEqual(self.client.post(self.edit_url, {}).status_code, 404)

    def test_post_updates_only_allowed_fields(self):
        self.client.force_login(self.user)
        other = User.objects.create_user(username="other", password="test-password")
        response = self.client.post(self.edit_url, {
            "last_name": "Петров", "first_name": "Пётр", "mid_name": "",
            "bio": "Новый текст", "user": other.pk, "is_published": "",
        })
        self.assertRedirects(response, reverse("users:employe_card", args=[self.employee.pk]))
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.last_name, "Петров")
        self.assertEqual(self.employee.bio, "Новый текст")
        self.assertEqual(self.employee.user, self.user)
        self.assertTrue(self.employee.is_published)

    def test_unsupported_method_is_rejected(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.put(self.edit_url, {}).status_code, 405)

    def test_owner_can_return_to_unpublished_card_after_editing(self):
        self.employee.is_published = False
        self.employee.save(update_fields=["is_published"])
        self.client.force_login(self.user)
        response = self.client.post(self.edit_url, {
            "last_name": "Иванов", "first_name": "Иван", "mid_name": "", "bio": "Текст",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Текст")

# Create your tests here.

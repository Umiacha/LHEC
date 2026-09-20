from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .forms import LoginForm
from .models import Employee


class UserLoginView(LoginView):
    template_name = 'users/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True


class UserLogoutView(LogoutView):
    next_page = reverse_lazy('core:home')


def people(request: HttpRequest) -> HttpResponse:
    """Страница со списком сотрудников."""
    employees = Employee.objects.published().by_position()
    return render(request, "core/people.html", {'employees': employees})


def employe_card(request: HttpRequest, pk: int):
    """Страница карточки сотрудника."""
    ...

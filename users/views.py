from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from django.db.models import Q

from research.models import ResearchDirection

from .forms import LoginForm, EmployeeEditForm
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
    return render(request, "users/people.html", {'employees': employees})


def employe_card(request: HttpRequest, pk: int) -> HttpResponse:
    """Страница карточки сотрудника."""
    employee = get_object_or_404(Employee, pk=pk)
    if not employee.is_published and (
        not request.user.is_authenticated or employee.user_id != request.user.pk
    ):
        employee = get_object_or_404(Employee.objects.published(), pk=pk)
    research_directions = ResearchDirection.objects.filter(
        Q(employees=employee) | Q(leader=employee),
        is_published=True,
    ).distinct()
    return render(request, "users/employee_card.html", {
        'employee': employee,
        'research_directions': research_directions,
    })


@login_required
@require_http_methods(["GET", "POST"])
def edit_employe_card(request: HttpRequest, pk: int) -> HttpResponse:  # TODO: потом добавить еще возможность выбирать свои featured publications
    """Редактирование владельцем своей карточки сотрудника."""
    employee = get_object_or_404(Employee, pk=pk, user=request.user)
    if request.method == 'POST':
        form = EmployeeEditForm(
            request.POST,
            request.FILES,
            instance=employee,
        )
        if form.is_valid():
            form.save()
            return redirect('users:employe_card', pk=pk)
    else:
        form = EmployeeEditForm(instance=employee)
    return render(
        request,
        'users/employee_edit.html',
        {'form': form, 'employee': employee},
    )

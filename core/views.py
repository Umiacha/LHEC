from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from publications.models import Publication
from research.models import Diploma, Dissertation, ResearchDirection, ResearchProject
from users.models import AcademicDegree, Employee, SciencePosition
from users.roles import INTERNAL_MATERIALS_PERMISSION

from .models import Announcement


def home(request: HttpRequest) -> HttpResponse:
    announcements = Announcement.objects.filter(
        is_published=True,
        published_at__lte=timezone.now()
    ).order_by('-published_at')[:3]
    return render(request, "core/home.html", {'announcements': announcements})


def about(request: HttpRequest) -> HttpResponse:
    return render(request, "core/about.html")


def history(request: HttpRequest) -> HttpResponse:
    scientific = Q(science_position__in=SciencePosition.values)
    staff_statistics = Employee.objects.current().staff().aggregate(  # TODO: Сейчас из-за разного числа сотрудников в тексте может быть дичь в падежах...
        total=Count('pk'),
        scientific=Count('pk', filter=scientific),
        doctors=Count('pk', filter=scientific & Q(
            academic_degree__in=AcademicDegree.doctors(),
        )),
        candidates=Count('pk', filter=scientific & Q(
            academic_degree__in=AcademicDegree.candidates(),
        )),
    )
    return render(request, "core/history.html", {'staff_statistics': staff_statistics})


def science(request: HttpRequest) -> HttpResponse:  # TODO: перенести этот view и url в research.
    year = timezone.localdate().year
    return render(request, "core/science.html", {
        "directions": ResearchDirection.objects.filter(is_published=True),
        "projects": ResearchProject.objects.filter(
            is_published=True, start_year__lte=year, end_year__gte=year,
        ),
        "publications": Publication.objects.filter(is_published=True, is_featured=True),
        "dissertations": Dissertation.objects.filter(is_published=True),
        "diplomas": Diploma.objects.filter(is_published=True).select_related("author").prefetch_related("supervisors"),
        "can_download_diplomas": request.user.has_perm(INTERNAL_MATERIALS_PERMISSION),
        "can_download_dissertations": request.user.has_perm(INTERNAL_MATERIALS_PERMISSION),
    })


# Проекты перенесены в research.views.
# def projects(request: HttpRequest) -> HttpResponse:
#     return render(request, "core/projects.html")


def publications(request: HttpRequest) -> HttpResponse:
    return render(request, "core/publications.html")


def news(request: HttpRequest) -> HttpResponse:
    return render(request, "core/news.html")


def gallery(request: HttpRequest) -> HttpResponse:
    return render(request, "core/gallery.html")


def contacts(request: HttpRequest) -> HttpResponse:
    return render(request, "core/contacts.html")

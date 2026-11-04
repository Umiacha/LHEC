from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from publications.models import Publication
from research.models import ResearchDirection
from users.models import AcademicDegree, Employee, SciencePosition

from .models import Announcement, GalleryPhoto


def home(request: HttpRequest) -> HttpResponse:
    announcements = Announcement.objects.filter(
        is_published=True,
        published_at__lte=timezone.now()
    ).order_by('-published_at')[:3]
    return render(request, "core/home.html", {
        'announcements': announcements,
        'directions': ResearchDirection.objects.filter(is_published=True),
        'homepage_publications': Publication.objects.filter(
            is_published=True, is_on_homepage=True,
        ).order_by('homepage_order', F('year').desc(nulls_last=True), '-pk'),
    })


def history(request: HttpRequest) -> HttpResponse:
    scientific = Q(science_position__in=SciencePosition.values)
    staff_statistics = Employee.objects.current().staff().aggregate(
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


def news(request: HttpRequest) -> HttpResponse:
    announcements = Announcement.objects.filter(
        is_published=True,
        published_at__lte=timezone.now(),
    ).order_by('-published_at', '-pk')
    page = Paginator(announcements, 10).get_page(request.GET.get('page'))
    return render(request, "core/news.html", {'page_obj': page})


def gallery(request: HttpRequest) -> HttpResponse:
    photos = GalleryPhoto.objects.filter(is_published=True)
    page = Paginator(photos, 24).get_page(request.GET.get('page'))
    return render(request, "core/gallery.html", {'page_obj': page})


def contacts(request: HttpRequest) -> HttpResponse:
    return render(request, "core/contacts.html")

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

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
    return render(request, "core/history.html")


def people(request: HttpRequest) -> HttpResponse:
    return render(request, "core/people.html")


def science(request: HttpRequest) -> HttpResponse:
    return render(request, "core/science.html")


def projects(request: HttpRequest) -> HttpResponse:
    return render(request, "core/projects.html")


def publications(request: HttpRequest) -> HttpResponse:
    return render(request, "core/publications.html")


def news(request: HttpRequest) -> HttpResponse:
    return render(request, "core/news.html")


def gallery(request: HttpRequest) -> HttpResponse:
    return render(request, "core/gallery.html")


def contacts(request: HttpRequest) -> HttpResponse:
    return render(request, "core/contacts.html")

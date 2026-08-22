from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "core/home.html")


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


def students(request: HttpRequest) -> HttpResponse:
    return render(request, "core/students.html")


def study_materials(request: HttpRequest) -> HttpResponse:
    return render(request, "core/study_materials.html")


def theses(request: HttpRequest) -> HttpResponse:
    return render(request, "core/theses.html")


def news(request: HttpRequest) -> HttpResponse:
    return render(request, "core/news.html")


def gallery(request: HttpRequest) -> HttpResponse:
    return render(request, "core/gallery.html")


def contacts(request: HttpRequest) -> HttpResponse:
    return render(request, "core/contacts.html")

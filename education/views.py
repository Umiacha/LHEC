from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def students(request: HttpRequest) -> HttpResponse:
    return render(request, "core/students.html")


def study_materials(request: HttpRequest) -> HttpResponse:
    return render(request, "core/study_materials.html")
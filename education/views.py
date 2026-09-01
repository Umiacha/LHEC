from pathlib import Path

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, FileResponse
from django.shortcuts import render, get_object_or_404

from .models import TeachingMaterial


def students(request: HttpRequest) -> HttpResponse:
    return render(request, "core/students.html")


def study_materials(request: HttpRequest) -> HttpResponse:
    return render(request, "core/study_materials.html")


def download_materials(request, pk):
    material = get_object_or_404(
        TeachingMaterial,
        pk=pk,
        is_published=True,
    )
    if (material.access_level == TeachingMaterial.AccessLevel.INTERNAL
        and not request.user.has_perm('education.view_internal_materials')):
        raise PermissionDenied
    return FileResponse(
        material.file.open('rb'),
        as_attachment=True,
        filename=Path(material.file.name).name,
    )

from pathlib import Path

from django.db.models import Prefetch
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, FileResponse, Http404
from django.shortcuts import render, get_object_or_404

from .models import TeachingMaterial, LabWork, LectureFile
from users.roles import INTERNAL_MATERIALS_PERMISSION


def download_lecture_file(request: HttpRequest, file_name: str) -> FileResponse:
    """Скачивание опубликованных лекций только сотрудниками и администраторами."""
    if not request.user.has_perm(INTERNAL_MATERIALS_PERMISSION):
        raise PermissionDenied
    attachment = get_object_or_404(
        LectureFile, file=file_name,
        lecture__is_published=True, lecture__course__is_published=True,
    )
    try:
        stream = attachment.file.open('rb')
    except FileNotFoundError:
        raise Http404('Файл не найден')
    return FileResponse(
        stream, as_attachment=True, filename=Path(attachment.file.name).name,
        content_type='application/octet-stream',
    )


def students(request: HttpRequest) -> HttpResponse:
    return render(request, "education/students.html")


def study_materials(request: HttpRequest) -> HttpResponse:
    can_view_internal = request.user.has_perm('education.view_internal_materials')
    visible_materials = TeachingMaterial.objects.filter(is_published=True)
    if not can_view_internal:
        visible_materials = visible_materials.filter(
            access_level=TeachingMaterial.AccessLevel.PUBLIC,
        )
    lab_works = LabWork.objects.filter(is_published=True).prefetch_related(
        Prefetch('materials', queryset=visible_materials.order_by('order', 'pk'), to_attr='visible_materials',)
    ).order_by('order', 'pk')
    standalone_materials = visible_materials.filter(lab_work__isnull=True,).order_by('order', 'pk')
    return render(
        request, "education/study_materials.html",
        {'lab_works': lab_works,
         'standalone_materials': standalone_materials,
         'can_view_internal': can_view_internal},
    )


def theses(request: HttpRequest) -> HttpResponse:
    return render(request, "education/theses.html")


def download_material(request, pk):
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

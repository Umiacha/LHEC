
from pathlib import Path

from django.db.models import Prefetch
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, FileResponse, Http404
from django.shortcuts import render, get_object_or_404
from django.views.decorators.cache import never_cache

from .models import TeachingMaterial, LabWork, LectureFile, LectureCourse, Lecture
from users.roles import INTERNAL_MATERIALS_PERMISSION


@never_cache
def download_lecture_file(request: HttpRequest, file_name: str) -> FileResponse:
    """Скачивание опубликованных лекций только сотрудниками и администраторами."""
    return _lecture_file_response(request, file_name)


@never_cache
def view_lecture_file(request: HttpRequest, file_name: str) -> FileResponse:
    """Просмотр PDF в браузере; остальные форматы скачиваются."""
    return _lecture_file_response(request, file_name, preview=True)


def _lecture_file_response(request, file_name, preview=False):  # TODO: а разве браузер сам не дает предпросмотр при попытке скачать PDF?.. Интересно.
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
    inline_pdf = preview and Path(attachment.file.name).suffix.lower() == '.pdf'
    response = FileResponse(
        stream, as_attachment=not inline_pdf, filename=Path(attachment.file.name).name,
        content_type='application/pdf' if inline_pdf else 'application/octet-stream',
    )
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@never_cache
def lecture_course_detail(request: HttpRequest, slug: str) -> HttpResponse:
    if not request.user.has_perm(INTERNAL_MATERIALS_PERMISSION):
        raise PermissionDenied
    course = get_object_or_404(
        LectureCourse.objects.select_related('lecturer').prefetch_related(
            Prefetch('lectures', queryset=Lecture.objects.filter(
                is_published=True,
            ).prefetch_related('files'), to_attr='visible_lectures'),
        ),
        slug=slug, is_published=True,
    )
    return render(request, 'education/lecture_course_detail.html', {'course': course})


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
    lecture_courses = (
        LectureCourse.objects.filter(is_published=True).select_related('lecturer')
        if can_view_internal else LectureCourse.objects.none()
    )
    return render(
        request, "education/study_materials.html",
        {'lab_works': lab_works,
         'standalone_materials': standalone_materials,
         'can_view_internal': can_view_internal,
         'lecture_courses': lecture_courses},
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

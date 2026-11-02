from django.utils.translation import gettext as _
from pathlib import Path
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.views.decorators.cache import never_cache
from users.roles import INTERNAL_MATERIALS_PERMISSION

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import Diploma, Dissertation, ProjectParticipation, ResearchDirection, ResearchProject


def direction_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """Страница научного направления."""
    direction = get_object_or_404(
        ResearchDirection.objects.select_related('leader'),
        slug=slug,
        is_published=True,
    )
    leader = direction.leader
    if leader is not None and not leader.is_published:
        leader = None
    employees = direction.employees.published().exclude(
        pk=direction.leader_id,
    ).by_position()
    publications = direction.publications.filter(is_published=True).order_by('-year', '-pk')
    page_obj = Paginator(publications, 20).get_page(request.GET.get('page'))
    return render(request, 'research/direction_detail.html', {
        'direction': direction,
        'leader': leader,
        'employees': employees,
        'publications': page_obj,
        'page_obj': page_obj,
    })


def projects(request: HttpRequest) -> HttpResponse:
    """Все опубликованные научные проекты, включая завершённые."""
    projects = ResearchProject.objects.filter(is_published=True)
    year = timezone.localdate().year
    current, completed, upcoming = [], [], []
    for project in projects:
        if project.end_year < year:
            completed.append(project)
        elif project.start_year > year:
            upcoming.append(project)
        else:
            current.append(project)
    groups = [
        {'title': _('Текущие'), 'projects': current, 'empty_message': _('Текущих проектов пока нет.')},
        {'title': _('Завершенные'), 'projects': completed, 'empty_message': _('Завершенных проектов пока нет.')},
    ]
    if upcoming:
        groups.append({'title': _('Предстоящие'), 'projects': upcoming})
    return render(request, 'research/projects_list.html', {'project_groups': groups})


def project_detail(request: HttpRequest, slug: str) -> HttpResponse:
    project = get_object_or_404(ResearchProject, slug=slug, is_published=True)
    participations = project.participations.select_related('employee').filter(
        Q(employee__isnull=True) | Q(employee__is_published=True),
    )
    return render(request, 'research/project_detail.html', {
        'project': project,
        'leader': next((entry for entry in participations if entry.role == ProjectParticipation.Role.LEADER), None),
        'executors': [entry for entry in participations if entry.role == ProjectParticipation.Role.EXECUTOR],
        'directions': project.research_directions.filter(is_published=True),
    })


@never_cache
def download_dissertation(request: HttpRequest, file_name: str) -> FileResponse:
    """
    Скачивание текста опубликованной диссертации.
    
    Только для сотрудников.
    """
    if not request.user.has_perm(INTERNAL_MATERIALS_PERMISSION):
        raise PermissionDenied
    dissertation = get_object_or_404(Dissertation, file=file_name, is_published=True)
    try:
        stream = dissertation.file.open('rb')
    except FileNotFoundError:
        raise Http404('Файл не найден')
    return FileResponse(stream, as_attachment=True, filename=Path(dissertation.file.name).name,
                        content_type='application/octet-stream')


@never_cache
def download_diploma(request: HttpRequest, file_name: str) -> FileResponse:
    """
    Скачивание текста опубликованной ВКР.
    
    Только для сотрудников.
    """
    if not request.user.has_perm(INTERNAL_MATERIALS_PERMISSION):
        raise PermissionDenied
    diploma = get_object_or_404(Diploma, file=file_name, is_published=True)
    try:
        stream = diploma.file.open('rb')
    except FileNotFoundError:
        raise Http404('Файл не найден')
    return FileResponse(
        stream, as_attachment=True, filename=Path(diploma.file.name).name,
        content_type='application/octet-stream',
    )

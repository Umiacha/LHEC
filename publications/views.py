from pathlib import Path

from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.views.decorators.cache import never_cache
from users.roles import INTERNAL_MATERIALS_PERMISSION
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse, FileResponse, Http404
from django.shortcuts import get_object_or_404

from .models import Publication, PublicationFile
from .forms import PublicationSearchForm


def publications(request: HttpRequest) -> HttpResponse:
    """Все публикации."""
    publs = Publication.objects.filter(is_published=True)
    form = PublicationSearchForm(request.GET)
    if form.is_valid():
        query = form.cleaned_data['q']
        if query:
            publs = publs.filter(
                Q(title__icontains=query) | Q(authors_text__icontains=query)
                | Q(venue__icontains=query) | Q(doi__icontains=query)
            )
        if employee := form.cleaned_data['employee']:
            publs = publs.filter(employees=employee)
        if year := form.cleaned_data['year']:
            publs = publs.filter(year=year)
        if direction := form.cleaned_data['direction']:
            publs = publs.filter(research_directions=direction)
    else:
        publs = publs.none()
    page = Paginator(publs.distinct(), 20).get_page(request.GET.get('page'))
    return render(
        request,
        'publications/publications_list.html',
        {
            'publications': page,
            'page_obj': page,
            'form': form,
            'has_filters': any(request.GET.get(key) for key in form.fields),
        }
    )


def publication(request: HttpRequest, pk: int) -> HttpResponse:
    """Страница публикации."""
    publ = get_object_or_404(Publication, pk=pk, is_published=True)
    return render(
        request,
        'publications/publication_card.html',
        {
            'publication': publ,
            'can_download_files': request.user.has_perm(INTERNAL_MATERIALS_PERMISSION),
        }
    )


@never_cache
def download_file(request: HttpRequest, file_name: str) -> FileResponse:
    """Файлы статей доступны только сотрудникам и администраторам."""
    if not request.user.has_perm(INTERNAL_MATERIALS_PERMISSION):
        raise PermissionDenied
    attachment = get_object_or_404(
        PublicationFile, file=file_name, publication__is_published=True,
    )
    try:
        stream = attachment.file.open('rb')
    except FileNotFoundError:
        raise Http404('Файл не найден')
    return FileResponse(
        stream, as_attachment=True, filename=Path(attachment.file.name).name,
        content_type='application/octet-stream',
    )

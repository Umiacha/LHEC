from pathlib import Path

from django.core.exceptions import PermissionDenied
from django.views.decorators.cache import never_cache
from users.roles import INTERNAL_MATERIALS_PERMISSION
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse, FileResponse, Http404
from django.shortcuts import get_object_or_404

from .models import Publication, PublicationFile


def publications(request: HttpRequest) -> HttpResponse:
    """Все публикации."""
    publs = Publication.objects.filter(is_published=True)
    return render(
        request,
        'publications/publications_list.html',
        {'publications': publs}
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

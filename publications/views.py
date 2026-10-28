from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404

from .models import Publication


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
        {'publication': publ}
    )


# TODO: разобрать все предложения из последнего сообщения чата из "Проверить структуру API-ручек"

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from .models import ResearchDirection


def direction_detail(request: HttpRequest, slug: str) -> HttpResponse:
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

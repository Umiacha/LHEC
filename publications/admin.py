from django.contrib import admin
from django.core.exceptions import PermissionDenied

from .forms import PublicationAdminForm, PublicationImportForm
from .importers import PublicationImportError, find_duplicates, parse_publication

from .models import Publication, PublicationFile


class PublicationFileInline(admin.TabularInline):
    model = PublicationFile
    extra = 1


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    form = PublicationAdminForm
    change_form_template = 'admin/publications/publication/change_form.html'

    def get_changeform_initial_data(self, request):
        return getattr(request, '_publication_import_initial',
                       super().get_changeform_initial_data(request))

    def add_view(self, request, form_url='', extra_context=None):
        context = dict(extra_context or {})
        context['import_form'] = PublicationImportForm()
        if request.method != 'POST' or '_import' not in request.POST:
            return super().add_view(request, form_url, context)
        if not self.has_add_permission(request):
            raise PermissionDenied
        upload_form = PublicationImportForm(request.POST, request.FILES)
        context['import_form'] = upload_form
        # Render an unsaved form after import, keeping unrelated entered fields.
        initial = request.POST.dict()
        for name in ('employees', 'research_directions'):
            initial[name] = request.POST.getlist(name)
        for name in ('is_published', 'is_featured', 'confirm_duplicate'):
            initial[name] = name in request.POST
        if upload_form.is_valid():
            upload = upload_form.cleaned_data['bibliography']
            extension = upload.name.rsplit('.', 1)[-1].lower()
            if extension not in {'bib', 'ris'}:
                upload_form.add_error('bibliography', 'Выберите файл .bib или .ris.')
            else:
                try:
                    result = parse_publication(upload, format=extension)
                except PublicationImportError as exc:
                    upload_form.add_error('bibliography', str(exc))
                else:
                    initial.update(result.data)
                    initial['confirm_duplicate'] = False
                    context['import_result'] = result
                    context['import_duplicates'] = find_duplicates(result)
        request._publication_import_initial = initial
        original_method = request.method
        request.method = 'GET'
        try:
            return super().add_view(request, form_url, context)
        finally:
            request.method = original_method
            del request._publication_import_initial

    inlines = (PublicationFileInline,)
    list_display = (
        'title',
        'year',
        'kind',
        'is_published',
        'is_featured',
    )
    list_filter = ('is_published', 'is_featured', 'kind', 'year', 'research_directions')
    search_fields = ('title', 'authors_text', 'venue', 'doi')
    filter_horizontal = ('employees', 'research_directions')
    readonly_fields = ('created_at', 'updated_at')

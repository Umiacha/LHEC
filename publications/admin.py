from django.contrib import admin

from .models import Publication, PublicationFile


class PublicationFileInline(admin.TabularInline):
    model = PublicationFile
    extra = 1


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    inlines = (PublicationFileInline,)
    list_display = (
        'title',
        'year',
        'kind',
        'is_published',
        'is_featured',
    )
    list_filter = ('is_published', 'is_featured', 'kind', 'year')
    search_fields = ('title', 'authors_text', 'venue', 'doi')
    filter_horizontal = ('employees',)
    readonly_fields = ('created_at', 'updated_at')

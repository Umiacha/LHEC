from django.contrib import admin

from .models import Announcement, GalleryPhoto
from django.utils.html import format_html


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'published_at',
        'is_published',
        'updated_at',
    )
    list_filter = (
        'is_published',
        'published_at',
    )
    search_fields = (
        'title',
        'text',
    )
    ordering = (
        '-published_at',
    )
    list_editable = (
        'is_published',
    )
    readonly_fields = (
        'created_at',
        'updated_at',
    )


admin.site.site_header = 'Администрирование сайта ЛХВЭ'
admin.site.site_title = 'ЛХВЭ'
admin.site.index_title = 'Управление сайтом'


@admin.register(GalleryPhoto)
class GalleryPhotoAdmin(admin.ModelAdmin):
    list_display = ('preview', 'caption', 'year', 'order', 'is_published')
    list_display_links = ('preview', 'caption')
    list_editable = ('order', 'is_published')
    list_filter = ('is_published', 'year')
    search_fields = ('caption',)
    readonly_fields = ('preview', 'created_at', 'updated_at')
    fields = ('image', 'preview', 'caption', 'year', 'order', 'is_published',
              'created_at', 'updated_at')

    @admin.display(description='Превью')
    def preview(self, obj):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" alt="" width="120" height="90" style="object-fit:contain">',
                obj.thumbnail.url,
            )
        return '—'

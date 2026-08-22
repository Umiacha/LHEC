from django.contrib import admin

from .models import Announcements


@admin.register(Announcements)
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
admin.site.title = 'ЛХВЭ'
admin.site.index_title = 'Управление сайтом'

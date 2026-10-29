from django.contrib import admin
from django.urls import reverse

from .models import ResearchDirection, ResearchMembership


class ResearchMembershipInline(admin.TabularInline):
    model = ResearchMembership
    autocomplete_fields = ('employee',)
    extra = 1
    verbose_name_plural = 'Участники (руководителя повторно добавлять не требуется)'


@admin.register(ResearchDirection)
class ResearchDirectionAdmin(admin.ModelAdmin):
    inlines = (ResearchMembershipInline,)
    list_display = ('name', 'leader', 'is_published', 'sort_order')
    list_display_links = ('name',)
    list_editable = ('is_published', 'sort_order')
    list_filter = ('is_published',)
    list_select_related = ('leader',)
    search_fields = (
        'name', 'description', 'leader__last_name', 'leader__first_name',
    )
    autocomplete_fields = ('leader',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Научное направление', {
            'fields': ('name', 'slug', 'description', 'leader'),
        }),
        ('Отображение на сайте', {
            'fields': ('is_published', 'sort_order'),
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def view_on_site(self, obj):
        if obj.is_published:
            return reverse('research:direction_detail', kwargs={'slug': obj.slug})
        return None

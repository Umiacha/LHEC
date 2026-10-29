from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.urls import reverse

from .models import Dissertation, ProjectParticipation, ResearchDirection, ResearchMembership, ResearchProject


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


class ProjectParticipationFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        leaders = 0
        people = set()
        for form in self.forms:
            data = form.cleaned_data
            if not data or data.get('DELETE'):
                continue
            if data.get('role') == ProjectParticipation.Role.LEADER:
                leaders += 1
            employee = data.get('employee')
            identity = (
                ('employee', employee.pk) if employee else
                ('external', form.instance.external_name, form.instance.external_organization)
            )
            if identity in people:
                raise ValidationError('Один человек не может участвовать в проекте дважды.')
            people.add(identity)
        if leaders > 1:
            raise ValidationError('У проекта может быть только один руководитель.')


class ProjectParticipationInline(admin.TabularInline):
    model = ProjectParticipation
    formset = ProjectParticipationFormSet
    autocomplete_fields = ('employee',)
    fields = ('role', 'employee', 'external_name', 'external_organization', 'sort_order')
    extra = 1
    verbose_name_plural = 'Участия в проекте: выберите сотрудника ЛХВЭ либо укажите ФИО и организацию внешнего участника'


@admin.register(ResearchProject)
class ResearchProjectAdmin(admin.ModelAdmin):
    inlines = (ProjectParticipationInline,)
    list_display = ('name', 'start_year', 'end_year', 'funding_source', 'is_published', 'sort_order')
    list_display_links = ('name',)
    list_editable = ('is_published', 'sort_order')
    list_filter = ('is_published', 'funding_kind', 'start_year', 'end_year', 'research_directions')
    search_fields = (
        'name', 'abstract', 'funding_source', 'funding_number', 'customer',
        'funding_program', 'participations__employee__last_name',
        'participations__employee__first_name', 'participations__external_name',
    )
    autocomplete_fields = ('research_directions',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Научный проект', {
            'fields': ('name', 'slug', ('start_year', 'end_year'), 'abstract', 'research_directions'),
        }),
        ('Финансирование', {
            'fields': ('funding_source',),
        }),
        ('Реквизиты проекта', {
            'fields': ('funding_kind', 'funding_number', 'customer', 'funding_program', 'external_url'),
            'classes': ('collapse',),
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
            return reverse('research:project_detail', kwargs={'slug': obj.slug})
        return None


@admin.register(Dissertation)
class DissertationAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'year', 'degree', 'is_published', 'sort_order')
    list_filter = ('is_published', 'degree', 'year')
    list_editable = ('is_published', 'sort_order')
    search_fields = ('title', 'author', 'specialty', 'supervisors')
    fields = ('title', 'external_url', 'author', 'year', 'degree', 'specialty', 'supervisors', 'file', 'is_published', 'sort_order')

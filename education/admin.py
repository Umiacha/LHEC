from django.contrib import admin

from .models import LabWork, TeachingMaterial, LectureCourse, Lecture, LectureFile, StudentWorkTopic


@admin.register(LabWork)
class LabWorkAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "order",
        "is_published",
    )
    list_editable = (
        "order",
        "is_published",
    )
    search_fields = ("title", "title_en")
    prepopulated_fields = {
        "slug": ("title",),
    }
    ordering = (
        "order",
        "title",
    )


@admin.register(TeachingMaterial)
class TeachingMaterialAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "lab_work",
        "access_level",
        "order",
        "is_published",
    )
    list_filter = (
        "access_level",
        "is_published",
    )
    search_fields = (
        "title",
        "description",
        "title_en",
    )
    ordering = (
        "order",
        "title",
    )


class LectureInline(admin.TabularInline):
    model = Lecture
    fields = ('title', 'title_en', 'order', 'is_published')
    extra = 0
    show_change_link = True


class LectureFileInline(admin.TabularInline):
    model = LectureFile
    fields = ('title', 'title_en', 'file', 'order')
    extra = 1


@admin.register(LectureCourse)
class LectureCourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'lecturer', 'order', 'is_published')
    list_editable = ('order', 'is_published')
    list_filter = ('is_published', 'lecturer')
    search_fields = ('title', 'title_en', 'description')
    prepopulated_fields = {'slug': ('title',)}
    list_select_related = ('lecturer',)
    inlines = (LectureInline,)


@admin.register(Lecture)
class LectureAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order', 'is_published', 'updated_at')
    list_editable = ('order', 'is_published')
    list_filter = ('course', 'is_published')
    search_fields = ('title', 'title_en', 'note', 'course__title', 'course__title_en')
    autocomplete_fields = ('course',)
    readonly_fields = ('updated_at',)
    list_select_related = ('course',)
    inlines = (LectureFileInline,)


@admin.register(StudentWorkTopic)
class StudentWorkTopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'title_en', 'kind', 'subject', 'sort_order', 'is_published')
    list_filter = ('kind', 'subject', 'is_published')
    list_editable = ('sort_order', 'is_published')
    search_fields = ('title', 'title_en')
    fields = ('title', 'title_en', 'kind', 'subject', 'sort_order', 'is_published')

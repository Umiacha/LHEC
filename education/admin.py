from django.contrib import admin

from .models import LabWork, TeachingMaterial


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
    search_fields = ("title",)
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
    )
    ordering = (
        "order",
        "title",
    )

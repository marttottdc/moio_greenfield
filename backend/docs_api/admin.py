"""
Admin configuration for Documentation models.
"""
from django.contrib import admin
from .models import GuideCategory, Guide, CodeExample, ApiEndpointNote


@admin.register(GuideCategory)
class GuideCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "order"]
    prepopulated_fields = {"slug": ("name",)}
    ordering = ["order", "name"]


@admin.register(Guide)
class GuideAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "is_published", "order", "updated_at"]
    list_filter = ["category", "is_published"]
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "summary", "content"]
    ordering = ["category__order", "order", "title"]
    
    fieldsets = (
        (None, {
            "fields": ("title", "slug", "category", "order")
        }),
        ("Content", {
            "fields": ("summary", "content"),
            "classes": ("wide",)
        }),
        ("Publishing", {
            "fields": ("is_published",)
        }),
    )


@admin.register(CodeExample)
class CodeExampleAdmin(admin.ModelAdmin):
    list_display = ["operation_id", "language", "title", "order"]
    list_filter = ["language"]
    search_fields = ["operation_id", "title", "code"]
    ordering = ["operation_id", "order"]


@admin.register(ApiEndpointNote)
class ApiEndpointNoteAdmin(admin.ModelAdmin):
    list_display = ["operation_id", "note_type", "title", "order"]
    list_filter = ["note_type"]
    search_fields = ["operation_id", "title", "content"]
    ordering = ["operation_id", "order"]

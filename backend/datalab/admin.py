"""
Django admin configuration for Data Lab models.
"""
from django.contrib import admin

from datalab.core.models import (
    AccumulationLog,
    DataSource,
    FileAsset,
    FileSet,
    ResultSet,
    Snapshot,
)
from datalab.crm_sources.models import CRMView
from datalab.panels.models import Panel, Widget


@admin.register(FileAsset)
class FileAssetAdmin(admin.ModelAdmin):
    """Admin for FileAsset."""
    list_display = ['id', 'filename', 'content_type', 'size', 'tenant', 'created_at']
    list_filter = ['content_type', 'created_at']
    search_fields = ['filename']
    readonly_fields = ['id', 'created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('tenant', 'uploaded_by')


@admin.register(FileSet)
class FileSetAdmin(admin.ModelAdmin):
    """Admin for FileSet."""
    list_display = ['id', 'name', 'tenant', 'file_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    filter_horizontal = ['files']
    
    def file_count(self, obj):
        return obj.files.count()
    file_count.short_description = 'File Count'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('tenant', 'last_snapshot').prefetch_related('files')


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    """Admin for DataSource."""
    list_display = ['id', 'name', 'type', 'tenant', 'created_at']
    list_filter = ['type', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('tenant')


@admin.register(ResultSet)
class ResultSetAdmin(admin.ModelAdmin):
    """Admin for ResultSet."""
    list_display = ['id', 'name', 'origin', 'row_count', 'storage', 'tenant', 'created_at']
    list_filter = ['origin', 'storage', 'created_at']
    search_fields = ['name']
    readonly_fields = ['id', 'schema_json', 'row_count', 'storage', 'storage_key', 'preview_json', 'lineage_json', 'created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('tenant', 'created_by')


@admin.register(Snapshot)
class SnapshotAdmin(admin.ModelAdmin):
    """Admin for Snapshot."""
    list_display = ['id', 'name', 'version', 'fileset', 'tenant', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['id', 'created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('tenant', 'resultset', 'fileset', 'created_by')


@admin.register(AccumulationLog)
class AccumulationLogAdmin(admin.ModelAdmin):
    """Admin for AccumulationLog."""
    list_display = ['id', 'fileset', 'snapshot', 'row_count_added', 'row_count_total', 'is_rebuild', 'created_at']
    list_filter = ['is_rebuild', 'created_at']
    readonly_fields = ['id', 'created_at']
    filter_horizontal = ['processed_files']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('tenant', 'snapshot', 'fileset').prefetch_related('processed_files')


@admin.register(CRMView)
class CRMViewAdmin(admin.ModelAdmin):
    """Admin for CRMView."""
    list_display = ['id', 'key', 'label', 'tenant', 'is_active', 'is_global', 'created_at']
    list_filter = ['is_active', 'is_global', 'created_at']
    search_fields = ['key', 'label', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('tenant')


@admin.register(Panel)
class PanelAdmin(admin.ModelAdmin):
    """Admin for Panel."""
    list_display = ['id', 'name', 'tenant', 'is_public', 'created_by', 'created_at']
    list_filter = ['is_public', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('tenant', 'created_by')


@admin.register(Widget)
class WidgetAdmin(admin.ModelAdmin):
    """Admin for Widget."""
    list_display = ['id', 'name', 'panel', 'widget_type', 'tenant', 'is_visible', 'order']
    list_filter = ['widget_type', 'is_visible', 'created_at']
    search_fields = ['name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('panel', 'tenant', 'created_by')
